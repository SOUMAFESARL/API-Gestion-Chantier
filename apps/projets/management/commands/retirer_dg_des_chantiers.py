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

from apps.core.contexte import contexte_entreprise
from apps.projets.services.affectations import retirer_dg_des_chantiers


class Command(BaseCommand):
    help = "Retire le DG des fonctions de chantier qu'il tient encore (sans --appliquer : décrit)."

    def add_arguments(self, parser):
        parser.add_argument("--entreprise", help="Une seule entreprise (slug).")
        parser.add_argument(
            "--appliquer", action="store_true", help="Applique les changements décrits."
        )

    def handle(self, *args, **options):
        from apps.entreprises.models import Entreprise

        entreprises = Entreprise.objects.all()
        if options.get("entreprise"):
            entreprises = entreprises.filter(slug=options["entreprise"])
        appliquer = options["appliquer"]
        for entreprise in entreprises.order_by("slug"):
            with contexte_entreprise(entreprise):
                constats = retirer_dg_des_chantiers(appliquer=appliquer)
            for constat in constats:
                self.stdout.write(f"{entreprise.slug} — {constat}")
        if not appliquer:
            self.stdout.write(
                self.style.WARNING("Rien n'a été modifié : relancez avec --appliquer.")
            )
