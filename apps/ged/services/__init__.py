"""Services du module « ged » — Gestion Documentaire CCD Digital (F6).

Point d'entrée unifié pour les opérations documentaires, le versioning,
la suppression sécurisée et les ponts automatiques.
"""

from apps.ged.services.documents import (
    ajouter_version,
    creer_document_automatique,
    deposer_document,
    supprimer_document,
)

__all__ = [
    "ajouter_version",
    "creer_document_automatique",
    "deposer_document",
    "supprimer_document",
]
