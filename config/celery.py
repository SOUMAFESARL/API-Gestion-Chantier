"""Application Celery — CCD Digital.

Attention multi-tenant : une tâche n'hérite pas du schéma de la requête qui
l'a déclenchée. Toute tâche qui touche des données métier doit recevoir le
nom du schéma en argument et l'activer explicitement :

    from django_tenants.utils import schema_context

    @shared_task
    def recalculer_avancement(code_schema, projet_id):
        with schema_context(code_schema):
            ...
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("ccd_digital")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def tache_de_verification(self):
    """Tâche de fumée : vérifie que le worker répond."""
    return f"worker actif — {self.request.id}"
