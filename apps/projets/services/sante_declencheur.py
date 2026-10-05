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
) -> bool:
    """Enregistre l'intention de recalcul et planifie la tâche Celery post-commit.

    Retourne True si une tâche a été planifiée, False si un recalcul était déjà en attente.
    """
    from apps.projets.tasks import recalculer_sante_projet_task

    schema_name = getattr(connection, "schema_name", "public")
    cle = obtenir_cle_recalcul_en_attente(schema_name, projet_id)

    # Déduplication réactive : si la clé existe déjà, un recalcul est déjà programmé
    # et traitera l'état le plus récent dès son exécution
    if cache.get(cle):
        logger.debug(
            "Recalcul de santé déjà en attente pour le projet %s (%s). Déclencheur %s ignoré.",
            projet_id,
            schema_name,
            declencheur_type,
        )
        return False

    cache.set(cle, 1, timeout=TTL_CLE_ATTENTE_SECONDES)

    declencheur_id_str = str(declencheur_id) if declencheur_id is not None else None
    projet_id_str = str(projet_id)

    def _planifier_tache():
        recalculer_sante_projet_task.delay(
            schema_name=schema_name,
            projet_id=projet_id_str,
            declencheur_type=declencheur_type,
            declencheur_id=declencheur_id_str,
        )

    transaction.on_commit(_planifier_tache)
    return True
