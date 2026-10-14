"""Relance par e-mail chaque chantier suivi dont le rapport du jour n'est pas remis.

À planifier à 17 h 30, du lundi au vendredi, à l'heure du chantier — par le cron
de l'hébergeur sur cPanel (Passenger ne lance pas Celery Beat) :

    30 17 * * 1-5  cd <racine> && python manage.py relancer_rapports_manquants

Une ligne déjà relancée dans la journée ne l'est pas une seconde fois.
"""

from django.core.management.base import BaseCommand

from apps.chantier.tasks import relancer_rapports_manquants_partout


class Command(BaseCommand):
    help = "Relance par e-mail les rapports journaliers du jour non remis, dans chaque entreprise."

    def add_arguments(self, parser):
        parser.add_argument("--schema", help="Une seule entreprise (nom de schéma).")

    def handle(self, *args, **options):
        bilan = relancer_rapports_manquants_partout(options.get("schema"))
        for schema, resultat in bilan.items():
            self.stdout.write(f"{schema} : {resultat}")
