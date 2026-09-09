"""Efface les traces d'un test d'inscription — DÉVELOPPEMENT UNIQUEMENT.

    python manage.py vider_inscription_test --tout --pour-de-vrai
    python manage.py vider_inscription_test --email essai@exemple.ci --pour-de-vrai

**Le problème.** Rejouer une inscription laisse derrière elle une entreprise,
son domaine, son abonnement d'essai, sa demande, et **un schéma PostgreSQL
entier**. Au bout de quelques essais la base est un cimetière, et le même nom
d'entreprise ne peut plus resservir.

**Trois pièges, et l'ordre de suppression les résume tous.**

1. `Entreprise.auto_drop_schema = False` — RG-06, on ne détruit jamais un schéma
   client. Supprimer la ligne ne supprime donc **pas** le schéma :
   `delete(force_drop=True)` est la seule forme qui emporte les deux.
2. Les demandes et les abonnements portent une clé étrangère `RESTRICT` vers
   l'entreprise. Les supprimer **après** elle échoue ; c'est ce que faisait la
   première écriture de cette commande.
3. `ModeleBase.delete()` est détourné vers une suppression **logique** — Socle
   §3.1. Une ligne « supprimée » existe encore physiquement, et `RESTRICT` la
   voit toujours. Il faut `supprimer_definitivement()`.

**Deux garde-fous.** La commande refuse de s'exécuter hors `DEBUG`, et les
schémas `public` et `demo` ne sont jamais candidats — supprimer le premier
rendrait `localhost` non résolvable, et plus aucune requête ne trouverait de
tenant.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import DemandeInscription, Entreprise

# Jamais candidats à la purge, sauf demande explicite pour le second.
SCHEMAS_PROTEGES = {"demo"}


class Command(BaseCommand):
    help = "Supprime les entreprises de test, leurs schémas et leurs traces."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="N'efface que ce qui vient de cette adresse.")
        parser.add_argument("--tout", action="store_true", help="Efface tout sauf les protégés.")
        parser.add_argument("--inclure-demo", action="store_true")
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

        proteges = set(SCHEMAS_PROTEGES)
        if options["inclure_demo"]:
            proteges.discard("demo")

        entreprises = self._candidates(options["email"], proteges)
        demandes = self._demandes(options["email"])

        for e in entreprises:
            self.stdout.write(f"  entreprise  {e.raison_sociale} — schéma « {e.schema_name} »")
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
        lot = Entreprise.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME)
        if proteges:
            lot = lot.exclude(schema_name__in=proteges)
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
        """**L'ordre est la seule chose qui compte ici.**

        Les enfants d'abord, définitivement, puis l'entreprise et son schéma.
        """
        from apps.billing.models import Abonnement

        for demande in demandes:
            demande.supprimer_definitivement()
        if demandes:
            self.stdout.write(self.style.SUCCESS(f"Supprimé : {len(demandes)} demande(s)."))

        for entreprise in entreprises:
            abonnements = list(Abonnement.tous_objets.filter(entreprise=entreprise))
            for abonnement in abonnements:
                abonnement.supprimer_definitivement()

            schema = entreprise.schema_name
            # `force_drop=True` : sans lui, `auto_drop_schema = False` laisse le
            # schéma en place et la ligne disparaît sans ses tables.
            entreprise.delete(force_drop=True)
            self.stdout.write(
                self.style.SUCCESS(f"Supprimé : schéma « {schema} », sa ligne et son abonnement.")
            )
