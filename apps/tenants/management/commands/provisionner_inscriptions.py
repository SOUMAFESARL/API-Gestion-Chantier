"""Commande de provisionnement des entreprises en attente — robuste pour cPanel.

Exécute le provisionnement des schémas PostgreSQL et des comptes administrateurs
pour les demandes d'inscription au statut PROVISIONNEMENT.

Peut être lancée :
1. De façon ponctuelle avec `--demande-id <UUID>` (déclenchée dès l'activation web).
2. De façon périodique via un Cron Job cPanel (filet de sécurité toutes les 2 minutes).
"""

import logging

from django.core.management.base import BaseCommand

from apps.tenants.models import DemandeInscription
from apps.tenants.services.inscription import provisionner

logger = logging.getLogger(__name__)


def _purger_comptes_test_temporaire(stdout, style):
    """Purge temporaire automatique des comptes et schémas de test spécifiques (ex: duzanf).
    
    Ce code est conçu pour s'exécuter automatiquement lors du déploiement en production,
    faire un nettoyage complet sans laisser d'orphelins, et pouvoir être retiré ensuite.
    """
    from django.db import connection, models, transaction
    from apps.billing.models import Abonnement
    from apps.tenants.models import DemandeInscription, Entreprise

    try:
        from apps.billing.models.facture import Facture
        from apps.billing.models.paiement import PaiementAbonnement
    except ImportError:
        Facture = None
        PaiementAbonnement = None

    try:
        from apps.billing.models.rappel_expiration import RappelExpiration
    except ImportError:
        RappelExpiration = None

    emails_cibles = ["duzanf@gmail.com", "duzanf2@gmail.com"]
    schemas_proteges = {"public", "demo"}

    try:
        demandes = list(
            DemandeInscription.tous_objets.filter(
                models.Q(email__in=[e.lower() for e in emails_cibles])
                | models.Q(slug_reserve__icontains="duzanf")
            )
        )

        entreprises = list(
            Entreprise.objects.filter(
                models.Q(email_contact__in=[e.lower() for e in emails_cibles])
                | models.Q(schema_name__icontains="duzanf")
            ).exclude(schema_name__in=schemas_proteges)
        )
        for d in demandes:
            if d.entreprise and d.entreprise not in entreprises and d.entreprise.schema_name not in schemas_proteges:
                entreprises.append(d.entreprise)

        if not demandes and not entreprises:
            return

        stdout.write(style.WARNING("\n[PURGE TEMPORAIRE] Données de test duzanf détectées. Purge en cours..."))

        with transaction.atomic():
            for e in entreprises:
                if Facture:
                    factures = list(Facture.tous_objets.filter(entreprise=e))
                    if PaiementAbonnement:
                        for f in factures:
                            for p in list(PaiementAbonnement.tous_objets.filter(facture=f)):
                                p.supprimer_definitivement()
                    for f in factures:
                        f.supprimer_definitivement()

                abonnements = list(Abonnement.tous_objets.filter(entreprise=e))
                if RappelExpiration:
                    for ab in abonnements:
                        for r in list(RappelExpiration.tous_objets.filter(abonnement=ab)):
                            r.supprimer_definitivement()
                for ab in abonnements:
                    ab.supprimer_definitivement()

            for d in demandes:
                d.supprimer_definitivement()
            if demandes:
                stdout.write(style.SUCCESS(f"  [OK] {len(demandes)} demande(s) d'inscription supprimée(s)."))

            for e in entreprises:
                nom_schema = e.schema_name
                e.delete(force_drop=True)
                stdout.write(
                    style.SUCCESS(f"  [OK] Entreprise « {e.raison_sociale} » et schéma « {nom_schema} » purgés.")
                )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name ILIKE '%duzanf%';"
            )
            orphelins = [row[0] for row in cursor.fetchall() if row[0] not in schemas_proteges]
            for schema_orphelin in orphelins:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_orphelin}" CASCADE;')
                stdout.write(style.SUCCESS(f"  [OK] Schéma orphelin « {schema_orphelin} » détruit."))

        stdout.write(style.SUCCESS("[PURGE TEMPORAIRE] Nettoyage très propre terminé avec succès.\n"))

    except Exception as exc:
        stdout.write(style.ERROR(f"[PURGE TEMPORAIRE] Erreur non bloquante : {exc}"))
        logger.exception("Erreur lors de la purge temporaire : %s", exc)


class Command(BaseCommand):
    help = "Provisionne les schémas PostgreSQL des demandes d'inscription en attente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demande-id",
            type=str,
            default=None,
            help="UUID de la demande d'inscription spécifique à provisionner.",
        )

    def handle(self, *args, **options):
        # Exécution de la purge temporaire de test
        _purger_comptes_test_temporaire(self.stdout, self.style)

        demande_id = options.get("demande_id")

        if demande_id:
            demandes = DemandeInscription.objects.filter(
                pk=demande_id,
                statut=DemandeInscription.Statut.PROVISIONNEMENT,
            )
            if not demandes.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Aucune demande en statut PROVISIONNEMENT trouvée pour l'ID : {demande_id}"
                    )
                )
                return
        else:
            demandes = DemandeInscription.objects.filter(
                statut=DemandeInscription.Statut.PROVISIONNEMENT
            ).order_by("cree_le")

        total = demandes.count()
        if total == 0:
            self.stdout.write("Aucune demande d'inscription en attente de provisionnement.")
            return

        self.stdout.write(f"Démarrage du provisionnement pour {total} demande(s)...")

        for demande in demandes:
            self.stdout.write(
                f"Traitement de la demande {demande.pk} (Entreprise : {demande.raison_sociale}, Schéma : {demande.slug_reserve})..."
            )
            try:
                provisionner(demande.pk)
                demande.refresh_from_db()
                if demande.statut == DemandeInscription.Statut.ACTIVEE:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Succès : Espace {demande.raison_sociale} provisionné avec succès."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Échec : La demande {demande.pk} s'est terminée avec le statut {demande.statut}."
                        )
                    )
            except Exception as exc:
                logger.exception("Erreur lors du provisionnement de la demande %s", demande.pk)
                self.stdout.write(
                    self.style.ERROR(
                        f"Erreur critique lors du provisionnement de {demande.pk} : {exc}"
                    )
                )
