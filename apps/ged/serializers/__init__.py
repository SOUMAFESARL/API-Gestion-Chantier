"""Serializers du module « ged »."""

from apps.ged.serializers.documents import (
    AuteurGedSerializer,
    DocumentDepotSerializer,
    DocumentGedDetailSerializer,
    DocumentGedSerializer,
    DocumentModificationSerializer,
    DocumentSuppressionSerializer,
    NouvelleVersionSerializer,
    SourceLiaisonSerializer,
    VersionDocumentSerializer,
)
from apps.ged.serializers.historique import EvenementAuditGedSerializer
from apps.ged.serializers.partages import (
    DocumentPartagePublicSerializer,
    PartageCreationSerializer,
    PartageDocumentSerializer,
)

__all__ = [
    "AuteurGedSerializer",
    "DocumentDepotSerializer",
    "DocumentGedDetailSerializer",
    "DocumentGedSerializer",
    "DocumentModificationSerializer",
    "DocumentPartagePublicSerializer",
    "DocumentSuppressionSerializer",
    "EvenementAuditGedSerializer",
    "NouvelleVersionSerializer",
    "PartageCreationSerializer",
    "PartageDocumentSerializer",
    "SourceLiaisonSerializer",
    "VersionDocumentSerializer",
]
