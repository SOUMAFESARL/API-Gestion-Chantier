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


_contextes_suspendus: dict[str, object] = {}


@task_prerun.connect
def _contexte_vierge(task_id=None, **_kwargs):
    """Chaque tâche part sans entreprise ni portée plateforme (D9)…"""
    from apps.core.contexte import suspendre_contexte

    _contextes_suspendus[task_id] = suspendre_contexte()


@task_postrun.connect
def _contexte_rendu(task_id=None, **_kwargs):
    """… et rend en partant celui qu'elle a trouvé.

    Sur un travailleur, c'est un contexte vide : une tâche qui aurait activé une entreprise sans
    bloc à refermer ne la lègue pas à la suivante. **En mode *eager*** (développement, cPanel), la
    tâche tourne dans le fil de la requête qui l'a lancée : la requête retrouve son entreprise.
    Une simple remise à zéro la lui retirait, et sa lecture suivante levait
    `HorsContexteEntreprise`. La session PostgreSQL suit d'elle-même (`apps.core.rls`).
    """
    from apps.core.contexte import reinitialiser_contexte, restaurer_contexte

    jeton = _contextes_suspendus.pop(task_id, None)
    if jeton is None:
        reinitialiser_contexte()
    else:
        restaurer_contexte(jeton)


@app.task(bind=True, ignore_result=True)
def tache_de_verification(self):
    """Tâche de fumée : vérifie que le worker répond."""
    return f"worker actif — {self.request.id}"
