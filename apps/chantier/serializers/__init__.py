"""Serializers du module « chantier ».

Journal de chantier : rapports journaliers, production, photos, blocages.
"""

from .rapport_journalier import (
    AuteurSimpleSerializer,
    ProjetSimpleSerializer,
    RapportJournalierCreateSerializer,
    RapportJournalierDetailSerializer,
    RapportJournalierListSerializer,
    RapportJournalierUpdateSerializer,
    RapportRejetSerializer,
    RapportValidationSerializer,
)
from .blocage import (
    BlocageCreateSerializer,
    BlocageResolutionSerializer,
    BlocageSerializer,
    BlocageUpdateSerializer,
)

__all__ = [
    "AuteurSimpleSerializer",
    "BlocageCreateSerializer",
    "BlocageResolutionSerializer",
    "BlocageSerializer",
    "BlocageUpdateSerializer",
    "ProjetSimpleSerializer",
    "RapportJournalierCreateSerializer",
    "RapportJournalierDetailSerializer",
    "RapportJournalierListSerializer",
    "RapportJournalierUpdateSerializer",
    "RapportRejetSerializer",
    "RapportValidationSerializer",
]
