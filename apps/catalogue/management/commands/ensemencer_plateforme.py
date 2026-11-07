"""Ensemence le catalogue de la plateforme sur une base neuve.

    python manage.py ensemencer_plateforme

Décision D9 (schéma unique) : la base de production repart de zéro, et les migrations aussi
(lot 6) — elles ne créent plus que les tables. Le catalogue, que les anciennes migrations
peuplaient en recopiant les tables des schémas d'entreprise, vient d'ici. `monter_base` appelle
cette commande sur une base sans catalogue.

Cette commande charge `apps/catalogue/fixtures/plateforme_initiale.json`, extrait de la base au
07/11/2026 : modules, permissions, modèles de rôles, référentiels, listes de valeurs, modèles de
découpage, plans d'abonnement et identité de la plateforme (341 objets, auteurs vidés).

**Elle refuse de tourner dès qu'une entreprise existe** : elle remplace le catalogue, et un
catalogue en usage ne se remplace pas.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

JEU = "plateforme_initiale"

# Dans l'ordre où l'on vide : les tables qui pointent vers les autres d'abord.
MODELES = [
    ("catalogue", "ModeleRoleModule"),
    ("catalogue", "LigneModelePlateforme"),
    ("catalogue", "NiveauModelePlateforme"),
    ("catalogue", "ModeleDecoupagePlateforme"),
    ("catalogue", "ValeurListePlateforme"),
    ("catalogue", "ListeValeursPlateforme"),
    ("catalogue", "ReferentielPlateforme"),
    ("catalogue", "ModeleRole"),
    ("catalogue", "CataloguePermission"),
    ("catalogue", "CatalogueModule"),
    ("billing", "Plan"),
    ("platform_admin", "IdentitePlateforme"),
]


class Command(BaseCommand):
    help = "Charge le catalogue complet de la plateforme sur une base sans entreprise."

    def handle(self, *args, **options):
        from django.apps import apps

        from apps.tenants.models import Entreprise

        entreprises = Entreprise.objects.exclude(schema_name="public").count()
        if entreprises:
            raise CommandError(
                f"{entreprises} entreprise(s) en base : le catalogue est en usage, il ne se "
                "remplace pas. Cette commande ne sert que sur une base neuve."
            )

        with transaction.atomic():
            for app_label, nom in MODELES:
                modele = apps.get_model(app_label, nom)
                # Suppression physique assumée : on remplace les semences partielles posées par
                # les migrations, sur une base sans aucune donnée d'entreprise.
                modele._base_manager.all().delete()
            call_command("loaddata", JEU, verbosity=0)

        for app_label, nom in reversed(MODELES):
            modele = apps.get_model(app_label, nom)
            self.stdout.write(f"  {app_label}.{nom} : {modele._base_manager.count()}")
        self.stdout.write(self.style.SUCCESS("Catalogue de la plateforme ensemencé."))
