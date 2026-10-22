r"""Évaluation de nuit du suivi d'avancement (F3), sans Celery.

Fait exactement ce que fait la tâche Celery Beat de 00 h 01
(`apps.projets.tasks.evaluer_f3_nuit_tous_tenants`) : rattrapage des rapports
approuvés non synchronisés, indice de santé, statuts et alertes de retard, pour
chaque entreprise active ou en essai.

Sur cPanel, où Celery Beat ne tourne pas, une tâche cron quotidienne à 00 h 01
l'appelle :

    cd /home/c2858133c/public_html/api-chantier && \
      /home/c2858133c/virtualenv/public_html/api-chantier/3.13/bin/python \
      manage.py evaluer_f3_nuit --settings=config.settings.cpanel
"""

from django.core.management.base import BaseCommand

from apps.projets.tasks import evaluer_f3_nuit_tous_tenants


class Command(BaseCommand):
    help = "Évaluation de nuit F3 (indice de santé, statuts, alertes) pour toutes les entreprises."

    def handle(self, *args, **options):
        resultat = evaluer_f3_nuit_tous_tenants()
        self.stdout.write(self.style.SUCCESS(f"Évaluation F3 terminée : {resultat}"))
