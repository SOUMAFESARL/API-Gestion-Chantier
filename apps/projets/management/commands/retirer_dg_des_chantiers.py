"""Retire le Directeur Général des fonctions de chantier qu'il tient encore.

Décision du 14/10/2026 : le DG garde ses attributions et ne tient aucune
fonction sur un chantier. Les données créées avant la règle peuvent encore le
désigner chef de projet ou conducteur de travaux ; cette commande les remet en
conformité, entreprise par entreprise.

    python manage.py retirer_dg_des_chantiers               # décrit seulement
    python manage.py retirer_dg_des_chantiers --appliquer   # applique

Rien n'est supprimé : les désignations sont retirées, les affectations
désactivées, et chaque DG concerné laisse une trace au journal d'audit.
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.projets.services.affectations import retirer_dg_des_chantiers


class Command(BaseCommand):
    help = "Retire le DG des fonctions de chantier qu'il tient encore (sans --appliquer : décrit)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", help="Une seule entreprise (nom de schéma).")
        parser.add_argument(
            "--appliquer", action="store_true", help="Applique les changements décrits."
        )

    def handle(self, *args, **options):
        from apps.tenants.models import Entreprise

        entreprises = Entreprise.objects.exclude(schema_name="public")
        if options.get("schema"):
            entreprises = entreprises.filter(schema_name=options["schema"])
        appliquer = options["appliquer"]
        for entreprise in entreprises.order_by("schema_name"):
            with schema_context(entreprise.schema_name):
                constats = retirer_dg_des_chantiers(appliquer=appliquer)
            for constat in constats:
                self.stdout.write(f"{entreprise.schema_name} — {constat}")
        if not appliquer:
            self.stdout.write(
                self.style.WARNING("Rien n'a été modifié : relancez avec --appliquer.")
            )
