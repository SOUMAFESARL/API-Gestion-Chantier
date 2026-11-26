"""Views du module « ged »."""

from apps.ged.views.documents import (
    DocumentDetailView,
    DocumentListCreateView,
    DocumentTelechargerView,
    DocumentVersionsView,
    DocumentVersionTelechargerView,
)
from apps.ged.views.historique import DocumentHistoriqueView, HistoriqueGlobalGedView
from apps.ged.views.partages import DocumentPartagesView, PartageDetailView
from apps.ged.views.public import PartagePublicDetailView, PartagePublicTelechargerView

__all__ = [
    "DocumentDetailView",
    "DocumentHistoriqueView",
    "DocumentListCreateView",
    "DocumentPartagesView",
    "DocumentTelechargerView",
    "DocumentVersionTelechargerView",
    "DocumentVersionsView",
    "HistoriqueGlobalGedView",
    "PartageDetailView",
    "PartagePublicDetailView",
    "PartagePublicTelechargerView",
]
