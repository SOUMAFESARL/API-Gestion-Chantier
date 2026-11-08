"""Recale les arbres de découpage : dates des parents, avancement, statuts.

Un parent lit ses enfants (décisions v1.2, amendement v1.3) : ses dates prévues, son avancement
et son statut « Clôturé » se **recalculent à chaque changement** d'un enfant. Les données écrites
**avant** cette règle, ou modifiées directement en base, n'ont jamais déclenché ce recalcul : leurs
parents restent sans dates et sans statut juste. Cette commande les rattrape, projet par projet,
dans le contexte de chaque entreprise ; elle est sans danger à relancer (idempotente).

    python manage.py recalculer_arbres                    # toutes les entreprises
    python manage.py recalculer_arbres --entreprise demo  # une seule
"""

from django.core.management.base import BaseCommand

from apps.core.contexte import contexte_entreprise


class Command(BaseCommand):
    help = "Recalcule les dates des parents, l'avancement et les statuts des arbres de projet."

    def add_arguments(self, parser):
        parser.add_argument("--entreprise", help="Slug d'une seule entreprise (défaut : toutes).")

    def handle(self, *args, **options):
        from apps.entreprises.models import Entreprise
        from apps.projets.models import Projet
        from apps.projets.services.avancement import recalculer_avancements_projet
        from apps.projets.services.dates_derivees import recalculer_dates_derivees
        from apps.projets.services.machine_etats import evaluer_statuts_arbre

        entreprises = Entreprise.objects.exclude(slug="")
        if options["entreprise"]:
            entreprises = entreprises.filter(slug=options["entreprise"])

        projets_traites = dates_recalees = statuts_changes = 0
        for entreprise in entreprises:
            with contexte_entreprise(entreprise):
                for projet in Projet.objects.filter(supprime_le__isnull=True):
                    # Les dates d'abord : le temporel d'un parent se lit sur elles.
                    dates_recalees += recalculer_dates_derivees(projet)
                    recalculer_avancements_projet(projet)
                    statuts_changes += evaluer_statuts_arbre(projet)
                    projets_traites += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{projets_traites} projet(s) recalé(s) : {dates_recalees} parent(s) re-daté(s), "
                f"{statuts_changes} statut(s) corrigé(s)."
            )
        )
