"""Application Celery — CCD Digital.

Attention multi-tenant : une tâche n'hérite pas du schéma de la requête qui
l'a déclenchée. Toute tâche qui touche des données métier doit recevoir le
nom du schéma en argument et l'activer explicitement :

    from apps.core.passerelle_schema import contexte_schema

    @shared_task
    def recalculer_avancement(code_schema, projet_id):
        with contexte_schema(code_schema):
            ...
"""

import os

from celery import Celery
from celery.signals import task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("ccd_digital")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@task_prerun.connect
@task_postrun.connect
def _contexte_vierge(**_kwargs):
    """Chaque tâche part sans entreprise ni portée plateforme, et n'en laisse aucune (D9).

    Un travailleur Celery enchaîne les tâches sur le même fil : sans cette remise à zéro, une
    tâche qui aurait activé une entreprise sans bloc à refermer la léguerait à la suivante. La
    session PostgreSQL suit d'elle-même, à la première requête (`apps.core.rls`).
    """
    from apps.core.contexte import reinitialiser_contexte

    reinitialiser_contexte()


@app.task(bind=True, ignore_result=True)
def tache_de_verification(self):
    """Tâche de fumée : vérifie que le worker répond."""
    return f"worker actif — {self.request.id}"
