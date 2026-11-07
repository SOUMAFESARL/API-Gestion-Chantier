"""Efface les traces d'un test d'inscription — DÉVELOPPEMENT UNIQUEMENT.

    python manage.py vider_inscription_test --tout --pour-de-vrai
    python manage.py vider_inscription_test --email essai@exemple.ci --pour-de-vrai

**Le problème.** Rejouer une inscription laisse derrière elle une entreprise, ses comptes, son
abonnement d'essai et sa demande. Au bout de quelques essais, la même adresse et le même nom
d'entreprise ne peuvent plus resservir.

Les entreprises passent par `supprimer_definitivement` (D9) : la même purge que celle du super
admin, calculée à partir des modèles. Les demandes sans entreprise se suppriment ensuite.

**Deux garde-fous.** La commande refuse de s'exécuter hors `DEBUG`, et l'entreprise `demo` n'est
jamais candidate.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.entreprises.models import DemandeInscription, Entreprise

# Jamais candidate à la purge (la suppression définitive la refuse aussi).
SLUGS_PROTEGES = {"demo"}


class Command(BaseCommand):
    help = "Supprime les entreprises de test et leurs traces."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="N'efface que ce qui vient de cette adresse.")
        parser.add_argument("--tout", action="store_true", help="Efface tout sauf les protégés.")
        parser.add_argument(
            "--pour-de-vrai",
            action="store_true",
            help="Exécute. Sans ce drapeau, la commande se contente de lister.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Commande de développement : elle refuse de s'exécuter avec DEBUG=False."
            )
        if not options["email"] and not options["tout"]:
            raise CommandError("Préciser --email <adresse> ou --tout.")

        proteges = set(SLUGS_PROTEGES)

        entreprises = self._candidates(options["email"], proteges)
        demandes = self._demandes(options["email"])

        for e in entreprises:
            self.stdout.write(f"  entreprise  {e.raison_sociale} — slug « {e.slug} »")
        for d in demandes:
            self.stdout.write(f"  demande     {d.email} — {d.statut}")

        if not entreprises and not demandes:
            self.stdout.write("Rien à effacer.")
            return

        if not options["pour_de_vrai"]:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("Rien n'a été supprimé. Ajouter --pour-de-vrai pour exécuter.")
            )
            return

        self._executer(entreprises, demandes)

    # -- Sélection ---------------------------------------------------------
    def _candidates(self, email, proteges):
        lot = Entreprise.objects.all()
        if proteges:
            lot = lot.exclude(slug__in=proteges)
        if email:
            lot = lot.filter(email_contact__iexact=email.strip())
        return list(lot)

    def _demandes(self, email):
        lot = DemandeInscription.tous_objets.all()
        if email:
            lot = lot.filter(email__iexact=email.strip())
        return list(lot)

    # -- Exécution ---------------------------------------------------------
    def _executer(self, entreprises, demandes):
        """Les entreprises d'abord (leur purge emporte leurs demandes), puis les demandes restantes."""
        from apps.entreprises.services.suppression_definitive import supprimer_definitivement

        for entreprise in entreprises:
            rapport = supprimer_definitivement(entreprise)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Supprimé : entreprise « {entreprise.slug} » "
                    f"({sum(rapport['tables_nettoyees'].values())} lignes)."
                )
            )

        restantes = [d for d in demandes if DemandeInscription.tous_objets.filter(pk=d.pk).exists()]
        for demande in restantes:
            demande.supprimer_definitivement()
        if restantes:
            self.stdout.write(self.style.SUCCESS(f"Supprimé : {len(restantes)} demande(s)."))
