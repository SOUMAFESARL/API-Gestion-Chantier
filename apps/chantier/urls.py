"""Routes pour l'application chantier — journal de chantier."""

from django.urls import path

from apps.chantier.views import (
    RapportDetailView,
    RapportListCreateView,
    RapportRejeterView,
    RapportSoumettreView,
    RapportValiderView,
)

app_name = "chantier"

urlpatterns = [
    path("rapports/", RapportListCreateView.as_view(), name="rapport-liste-creer"),
    path("rapports/<uuid:pk>/", RapportDetailView.as_view(), name="rapport-detail"),
    path(
        "rapports/<uuid:pk>/soumettre/",
        RapportSoumettreView.as_view(),
        name="rapport-soumettre",
    ),
    path(
        "rapports/<uuid:pk>/valider/",
        RapportValiderView.as_view(),
        name="rapport-valider",
    ),
    path(
        "rapports/<uuid:pk>/rejeter/",
        RapportRejeterView.as_view(),
        name="rapport-rejeter",
    ),
]
