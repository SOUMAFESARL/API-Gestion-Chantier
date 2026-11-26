"""Modèles de l'application GED — Gestion Documentaire (Module 11).

Entités F6 (synthèse validée + Sprint 5) :
- Document : classeur projet, 6 catégories BTP, référence, automatique inaltérable
- VersionDocument : historique sans perte v1 -> v2..., max 50 Mo, stockage privé, hash SHA-256
- LiaisonDocument : traçabilité des ponts automatiques F1, F2, F9
- PartageDocument : lien temporaire externe 72 h consultable sans compte
"""

from apps.ged.models.document import CategorieDocument, Document
from apps.ged.models.exceptions import (
    DocumentAutomatiqueNonModifiable,
    DocumentAutomatiqueNonSupprimable,
    FormatFichierNonAutorise,
    PartageExpire,
    SuppressionVersionInterdite,
    TailleFichierDepassee,
)
from apps.ged.models.liaison_document import LiaisonDocument, TypeSourceDocument, TypeSourceLiaison
from apps.ged.models.partage_document import (
    DUREE_PARTAGE_HEURES,
    PartageDocument,
    expiration_par_defaut,
    generer_jeton_partage,
)
from apps.ged.models.version_document import (
    EXTENSIONS_AUTORISEES,
    TAILLE_MAX_OCTETS,
    VersionDocument,
    calculer_hash_fichier,
    chemin_version_document,
)

__all__ = [
    "DUREE_PARTAGE_HEURES",
    "EXTENSIONS_AUTORISEES",
    "TAILLE_MAX_OCTETS",
    "CategorieDocument",
    "Document",
    "DocumentAutomatiqueNonModifiable",
    "DocumentAutomatiqueNonSupprimable",
    "FormatFichierNonAutorise",
    "LiaisonDocument",
    "PartageDocument",
    "PartageExpire",
    "SuppressionVersionInterdite",
    "TailleFichierDepassee",
    "TypeSourceDocument",
    "TypeSourceLiaison",
    "VersionDocument",
    "calculer_hash_fichier",
    "chemin_version_document",
    "expiration_par_defaut",
    "generer_jeton_partage",
]
