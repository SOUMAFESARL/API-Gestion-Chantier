"""Service de déclenchement réactif du recalcul de l'indice de santé de projet.

Conformément à la spécification (C8) :
- Pas de recalcul synchrone bloquant les requêtes HTTP.
- Clé Redis 'en attente' pour dédupliquer les déclenchements consécutifs.
- Déclenchement via transaction.on_commit vers la tâche Celery recalculer_sante_projet_task.
"""

import logging
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db import connection, transaction

logger = logging.getLogger(__name__)

CLE_PREFIX_ATTENTE = "sante:recalcul_en_attente"
TTL_CLE_ATTENTE_SECONDES = 300  # 5 minutes de TTL de sécurité


def obtenir_cle_recalcul_en_attente(schema_name: str, projet_id: Any) -> str:
    """Construit la clé Redis identifiant un recalcul en attente pour un projet."""
    return f"{CLE_PREFIX_ATTENTE}:{schema_name}:{str(projet_id)}"


def declencher_recalcul_sante(
    projet_id: UUID | str,
    declencheur_type: str,
    declencheur_id: Any | None = None,
) -> None:
    """Enregistre l'intention de recalcul et planifie la tâche Celery post-commit (C8 / F2).

    Règles de concurrence et déduplication :
    1. cache.add est exécuté DANS le callback on_commit pour éviter de poser un verrou orphelin
       si la transaction courante est annulée (rollback).
    2. Si la clé est posée avec succès, la tâche est planifiée avec un countdown de 10s pour regrouper
       les rafales d'événements.
    3. Si la clé existe déjà, la tâche déjà planifiée recalculera l'état le plus récent.
    """
    from apps.projets.tasks import recalculer_sante_projet_task

    schema_name = getattr(connection, "schema_name", "public")
    cle = obtenir_cle_recalcul_en_attente(schema_name, projet_id)
    declencheur_id_str = str(declencheur_id) if declencheur_id is not None else None
    projet_id_str = str(projet_id)

    def _planifier_apres_commit():
        cle_posee = cache.add(cle, 1, timeout=TTL_CLE_ATTENTE_SECONDES)
        if cle_posee:
            recalculer_sante_projet_task.apply_async(
                kwargs={
                    "schema_name": schema_name,
                    "projet_id": projet_id_str,
                    "declencheur_type": declencheur_type,
                    "declencheur_id": declencheur_id_str,
                },
                countdown=10,
            )
            logger.debug(
                "Tâche de recalcul santé planifiée pour le projet %s (%s, déclencheur %s, countdown 10s).",
                projet_id_str,
                schema_name,
                declencheur_type,
            )
        else:
            logger.debug(
                "Recalcul santé déjà en attente pour le projet %s (%s). Déclencheur %s absorbé.",
                projet_id_str,
                schema_name,
                declencheur_type,
            )

    transaction.on_commit(_planifier_apres_commit)

