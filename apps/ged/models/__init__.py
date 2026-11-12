"""Modèles de l'application GED — Gestion Documentaire (Module 11).

Entités F6 MVP (synthèse validée le 12/11/2026) :
- Document : classeur projet, 6 catégories BTP, référence, automatique inaltérable
- VersionDocument : historique sans perte v1 -> v2..., max 50 Mo, hash SHA-256
- LiaisonDocument : traçabilité des ponts automatiques F1, F2, F9
"""

from apps.ged.models.document import CategorieDocument, Document
from apps.ged.models.exceptions import (
    DocumentAutomatiqueNonSupprimable,
    FormatFichierNonAutorise,
    SuppressionVersionInterdite,
    TailleFichierDepassee,
)
from apps.ged.models.liaison_document import LiaisonDocument, TypeSourceDocument, TypeSourceLiaison
from apps.ged.models.version_document import (
    EXTENSIONS_AUTORISEES,
    TAILLE_MAX_OCTETS,
    VersionDocument,
    calculer_hash_fichier,
    chemin_version_document,
)

__all__ = [
    "EXTENSIONS_AUTORISEES",
    "TAILLE_MAX_OCTETS",
    "CategorieDocument",
    "Document",
    "DocumentAutomatiqueNonSupprimable",
    "FormatFichierNonAutorise",
    "LiaisonDocument",
    "SuppressionVersionInterdite",
    "TailleFichierDepassee",
    "TypeSourceDocument",
    "TypeSourceLiaison",
    "VersionDocument",
    "calculer_hash_fichier",
    "chemin_version_document",
]
