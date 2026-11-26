"""Services du module « ged » — Gestion Documentaire CCD Digital (F6).

Point d'entrée unifié pour les opérations documentaires, le versioning,
la suppression sécurisée, le partage externe 72 h, l'audit et les ponts automatiques.
"""

from apps.ged.services.audit import journaliser_evenement_ged
from apps.ged.services.documents import (
    ajouter_version,
    creer_document_automatique,
    deposer_document,
    modifier_document,
    supprimer_document,
)
from apps.ged.services.partages import (
    creer_partage_document,
    enregistrer_telechargement_partage_public,
    ouvrir_partage_public,
    revoquer_partage_document,
)

__all__ = [
    "ajouter_version",
    "creer_document_automatique",
    "creer_partage_document",
    "deposer_document",
    "enregistrer_telechargement_partage_public",
    "journaliser_evenement_ged",
    "modifier_document",
    "ouvrir_partage_public",
    "revoquer_partage_document",
    "supprimer_document",
]
