"""Commande de rattrapage (backfill) idempotente de la GED — CCD Digital (F6).

Usage :
    python manage.py synchroniser_ged
    python manage.py synchroniser_ged --entreprise demo
    python manage.py synchroniser_ged --dry-run

Responsabilités :
1. Rejoue dans l'ordre chronologique les pièces F1/F2 existantes en base avant
   activation des signaux GED :
   - Contrats du marché (`ProjetContrat`, triés par `version ASC, cree_le ASC`)
   - Ordres de service de démarrage (`Projet.ordre_service`)
   - Avenants actifs (`Avenant.document` et `Avenant.ordre_service`)
   - Rapports journaliers approuvés (`RapportJournalier` statut `APPROUVE`)
   sans envoyer de notifications de masse (`notifier=False`).
2. Migre vers le coffre privé `StockageGed` tout fichier de `VersionDocument`
   qui résiderait encore sous l'ancien stockage public `MEDIA_ROOT`.
3. Strictement idempotent : relancer la commande ne crée aucun doublon.
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import BaseCommand

from apps.chantier.models import RapportJournalier
from apps.core.contexte import contexte_entreprise, portee_plateforme
from apps.core.enums import StatutRapport
from apps.entreprises.models import Entreprise
from apps.ged.models import VersionDocument
from apps.ged.services.archivage_auto import (
    archiver_avenant,
    archiver_contrat_projet,
    archiver_ordre_service_projet,
    archiver_rapport_approuve,
)
from apps.ged.storage import StockageGed
from apps.projets.models import Avenant, Projet, ProjetContrat


class Command(BaseCommand):
    help = (
        "Synchronise de manière idempotente les pièces existantes (Contrats, OS, Avenants, "
        "Rapports approuvés) dans la GED et migre les fichiers vers le stockage privé."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--entreprise",
            dest="slug",
            default="",
            help="Restreindre la synchronisation à une seule entreprise (slug).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les volumes à traiter sans écrire en base ni sur disque.",
        )

    def handle(self, *args, **options):
        slug = (options.get("slug") or "").strip()
        dry_run = bool(options.get("dry_run"))

        with portee_plateforme(motif="synchronisation_ged_initiale"):
            qs_entreprises = Entreprise.objects.order_by("slug")
            if slug:
                qs_entreprises = qs_entreprises.filter(slug=slug)
            entreprises = list(qs_entreprises)

        if not entreprises:
            self.stdout.write(self.style.WARNING("Aucune entreprise trouvée à synchroniser."))
            return

        totaux = {
            "entreprises": 0,
            "contrats": 0,
            "ordres_service": 0,
            "avenants": 0,
            "rapports": 0,
            "fichiers_migres_prive": 0,
        }

        for entreprise in entreprises:
            totaux["entreprises"] += 1
            with contexte_entreprise(entreprise.pk):
                bilan = self._synchroniser_entreprise(entreprise, dry_run=dry_run)
                for cle, valeur in bilan.items():
                    totaux[cle] += valeur

        mode = "SIMULATION (--dry-run)" if dry_run else "TERMINÉ"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] Synchronisation GED : "
                f"{totaux['entreprises']} entreprise(s), "
                f"{totaux['contrats']} contrat(s), "
                f"{totaux['ordres_service']} OS, "
                f"{totaux['avenants']} avenant(s), "
                f"{totaux['rapports']} rapport(s) approuvé(s), "
                f"{totaux['fichiers_migres_prive']} fichier(s) déplacé(s) vers le coffre privé."
            )
        )

    def _synchroniser_entreprise(self, entreprise: Entreprise, *, dry_run: bool) -> dict[str, int]:
        stats = {
            "contrats": 0,
            "ordres_service": 0,
            "avenants": 0,
            "rapports": 0,
            "fichiers_migres_prive": 0,
        }

        projets = list(Projet.objects.select_related("entreprise", "cree_par").order_by("cree_le"))

        for projet in projets:
            # 1. Contrats dans l'ordre exact des versions (v1 -> v2 -> v3...)
            contrats = list(
                ProjetContrat.objects.select_related("projet", "cree_par")
                .filter(projet=projet)
                .exclude(fichier="")
                .order_by("version", "cree_le")
            )
            for contrat in contrats:
                stats["contrats"] += 1
                if not dry_run:
                    archiver_contrat_projet(contrat, notifier=False)

            # 2. Ordre de service de démarrage du projet
            if projet.ordre_service:
                stats["ordres_service"] += 1
                if not dry_run:
                    archiver_ordre_service_projet(projet, notifier=False)

            # 3. Avenants actifs du projet
            avenants = list(
                Avenant.objects.select_related("projet", "cree_par")
                .filter(projet=projet)
                .order_by("date_signature", "cree_le")
            )
            for avenant in avenants:
                if avenant.document or avenant.ordre_service:
                    stats["avenants"] += 1
                    if not dry_run:
                        archiver_avenant(avenant, notifier=False)

        # 4. Rapports journaliers approuvés (F2 -> F6)
        rapports = list(
            RapportJournalier.objects.select_related(
                "projet", "projet__entreprise", "auteur", "valide_par"
            )
            .filter(statut=StatutRapport.APPROUVE, projet__supprime_le__isnull=True)
            .order_by("date_rapport", "cree_le")
        )
        for rapport in rapports:
            stats["rapports"] += 1
            if not dry_run:
                archiver_rapport_approuve(rapport, notifier=False)

        # 5. Migration vers le coffre privé (StockageGed) des fichiers locaux sous MEDIA_ROOT
        if isinstance(default_storage, FileSystemStorage):
            coffre = StockageGed()._backend()
            versions = VersionDocument.tous_objets.exclude(fichier="")
            for version in versions.iterator():
                chemin = version.fichier.name
                if not chemin:
                    continue
                if not coffre.exists(chemin) and default_storage.exists(chemin):
                    stats["fichiers_migres_prive"] += 1
                    if not dry_run:
                        with default_storage.open(chemin, "rb") as src:
                            contenu = src.read()
                        coffre.save(chemin, ContentFile(contenu))
                        default_storage.delete(chemin)

        return stats
