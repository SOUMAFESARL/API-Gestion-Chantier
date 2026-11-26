"""Routage REST du module Gestion Documentaire (GED / F6)."""

from django.urls import path

from apps.ged.views import (
    DocumentDetailView,
    DocumentHistoriqueView,
    DocumentListCreateView,
    DocumentPartagesView,
    DocumentTelechargerView,
    DocumentVersionsView,
    DocumentVersionTelechargerView,
    HistoriqueGlobalGedView,
    PartageDetailView,
    PartagePublicDetailView,
    PartagePublicTelechargerView,
)

app_name = "ged"

urlpatterns = [
    # Classeur GED authentifié (tâches 3.3, 3.6, 3.8, 3.11)
    path("ged/documents/", DocumentListCreateView.as_view(), name="document-list"),
    path("ged/documents/<uuid:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path(
        "ged/documents/<uuid:pk>/versions/",
        DocumentVersionsView.as_view(),
        name="document-versions",
    ),
    path(
        "ged/documents/<uuid:pk>/telecharger/",
        DocumentTelechargerView.as_view(),
        name="document-telecharger",
    ),
    path(
        "ged/documents/<uuid:pk>/versions/<uuid:version_id>/telecharger/",
        DocumentVersionTelechargerView.as_view(),
        name="document-version-telecharger",
    ),
    path(
        "ged/documents/<uuid:pk>/historique/",
        DocumentHistoriqueView.as_view(),
        name="document-historique",
    ),
    path(
        "ged/historique/",
        HistoriqueGlobalGedView.as_view(),
        name="historique-global",
    ),
    # Partage externe temporaire 72 h (tâche 3.9)
    path(
        "ged/documents/<uuid:pk>/partages/",
        DocumentPartagesView.as_view(),
        name="document-partages",
    ),
    path(
        "ged/partages/<uuid:partage_id>/",
        PartageDetailView.as_view(),
        name="partage-detail",
    ),
    # Consultation & téléchargement publics anonymes (sans JWT, D9 via jeton)
    path(
        "public/partages/<str:jeton>/",
        PartagePublicDetailView.as_view(),
        name="partage-public-detail",
    ),
    path(
        "public/partages/<str:jeton>/telecharger/",
        PartagePublicTelechargerView.as_view(),
        name="partage-public-telecharger",
    ),
]
