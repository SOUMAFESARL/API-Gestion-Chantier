"""Service de déclenchement réactif du recalcul de l'indice de santé de projet.

Exécution directe en Python après validation de la transaction (`transaction.on_commit`),
sans aucune dépendance à Redis, au cache ni au broker Celery.
"""

import logging
from typing import Any
from uuid import UUID

from django.db import connection, transaction

from apps.core.contexte import exiger_entreprise

logger = logging.getLogger(__name__)

CLE_PREFIX_ATTENTE = "sante:recalcul_en_attente"
TTL_CLE_ATTENTE_SECONDES = 300


def obtenir_cle_recalcul_en_attente(entreprise_id: Any, projet_id: Any) -> str:
    """Construit l'identifiant de déduplication d'un recalcul de santé pour un projet."""
    return f"{CLE_PREFIX_ATTENTE}:{entreprise_id}:{str(projet_id)}"


def declencher_recalcul_sante(
    projet_id: UUID | str,
    declencheur_type: str,
    declencheur_id: Any | None = None,
) -> None:
    """Planifie le recalcul de l'indice de santé directement en post-commit, sans Redis ni Celery."""
    from apps.projets.tasks import recalculer_sante_projet_task

    entreprise_id = str(exiger_entreprise())
    cle = obtenir_cle_recalcul_en_attente(entreprise_id, projet_id)
    declencheur_id_str = str(declencheur_id) if declencheur_id is not None else None
    projet_id_str = str(projet_id)

    en_attente: set[str] = getattr(connection, "_sante_recalculs_en_attente", None)
    if en_attente is None:
        en_attente = set()
        connection._sante_recalculs_en_attente = en_attente

    if cle in en_attente:
        return
    en_attente.add(cle)

    def _executer_apres_commit():
        en_attente.discard(cle)
        try:
            recalculer_sante_projet_task(
                entreprise_id=entreprise_id,
                projet_id=projet_id_str,
                declencheur_type=declencheur_type,
                declencheur_id=declencheur_id_str,
            )
        except Exception:
            logger.exception(
                "Échec du recalcul de santé post-commit pour le projet %s (%s).",
                projet_id_str,
                entreprise_id,
            )

    transaction.on_commit(_executer_apres_commit)

