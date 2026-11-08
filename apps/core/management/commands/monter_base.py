"""Monte une base neuve en une commande (D9, lot 6).

    python manage.py monter_base
    python manage.py monter_base --super-admin support@ccd-digital.ci
    python manage.py monter_base --demo demo beta                # développement seulement

Sur une base **vide** (créée, sans table), dans l'ordre :

1. `migrate`, une passe depuis les `0001` ;
2. `verifier_isolation` : la RLS est en place sur toutes les tables d'entreprise, le rôle de
   connexion la subit, le rôle de la portée plateforme existe ;
3. `ensemencer_plateforme` : catalogue, modèles de rôles, référentiels, listes, modèles de
   découpage, plans, identité de la plateforme — **sauté si le catalogue est déjà là** ;
4. `charger_jours_feries` pour l'année en cours et la suivante ;
5. avec `--super-admin` : le compte du personnel CCD Digital (Q4, Q8), entreprise nulle. Le mot de
   passe se lit dans la variable d'environnement `CCD_SUPER_ADMIN_MOTDEPASSE`, jamais sur la
   ligne de commande, qui reste dans l'historique du terminal ;
6. avec `--demo` (refusé quand `DEBUG` est faux) : pour chaque slug, `creer_entreprise_demo` puis
   `peupler_donnees_test` puis `completer_donnees_locales`. Deux entreprises (`demo beta`) donnent ce dont la suite d'étanchéité a
   besoin.

Rejouable : chaque étape converge, et une base déjà montée n'est que vérifiée.

**Prérequis, une fois par serveur** : `scripts/sql/roles_rls.sql`, joué en superutilisateur, crée
le rôle `ccd_plateforme`. Les droits par base, eux, sont redonnés par la migration RLS.
"""

import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

VARIABLE_MOT_DE_PASSE = "CCD_SUPER_ADMIN_MOTDEPASSE"


class Command(BaseCommand):
    help = "Monte une base neuve : migrations, contrôle d'isolation, ensemencement."

    def add_arguments(self, parser):
        parser.add_argument(
            "--super-admin",
            metavar="EMAIL",
            help=f"Compte du personnel CCD Digital (mot de passe : ${VARIABLE_MOT_DE_PASSE}).",
        )
        parser.add_argument(
            "--demo",
            nargs="+",
            metavar="SLUG",
            help="Entreprises de démonstration à créer et peupler (développement seulement).",
        )

    def handle(self, *args, **options):
        if options["demo"] and not settings.DEBUG:
            raise CommandError("--demo est réservé au développement : refusé quand DEBUG est faux.")
        mot_de_passe = None
        if options["super_admin"]:
            mot_de_passe = os.environ.get(VARIABLE_MOT_DE_PASSE)
            if not mot_de_passe:
                raise CommandError(
                    f"--super-admin : la variable d'environnement {VARIABLE_MOT_DE_PASSE} est vide."
                )

        self._etape("Migrations")
        call_command("migrate", interactive=False, verbosity=1)

        self._etape("Isolation")
        call_command("verifier_isolation")

        self._etape("Catalogue de la plateforme")
        from apps.catalogue.models import CatalogueModule

        if CatalogueModule._base_manager.exists():
            self.stdout.write("  Déjà ensemencé : laissé tel quel.")
        else:
            call_command("ensemencer_plateforme")

        self._etape("Jours fériés")
        annee = timezone.localdate().year
        call_command("charger_jours_feries", annees=[annee, annee + 1])

        if options["super_admin"]:
            self._etape("Personnel CCD Digital")
            call_command("creer_super_admin", email=options["super_admin"], motdepasse=mot_de_passe)

        for slug in options["demo"] or []:
            self._etape(f"Entreprise de démonstration « {slug} »")
            call_command("creer_entreprise_demo", entreprise=slug)
            call_command("peupler_donnees_test", entreprise=slug)
            call_command("completer_donnees_locales", entreprise=[slug])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Base montée."))

    def _etape(self, titre: str) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"— {titre}"))
