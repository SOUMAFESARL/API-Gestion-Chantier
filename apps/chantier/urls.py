"""Routes pour l'application chantier — journal de chantier."""

from django.urls import path

from apps.chantier.views import (
    BlocageDetailView,
    BlocagePrendreEnChargeView,
    BlocageResoudreView,
    ProjetBlocageListCreateView,
    RapportDetailView,
    RapportListCreateView,
    RapportRejeterView,
    RapportSoumettreView,
    RapportValiderView,
)

app_name = "chantier"

urlpatterns = [
    # Rapports journaliers
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
    # Blocages de chantier
    path(
        "projets/<uuid:projet_id>/blocages/",
        ProjetBlocageListCreateView.as_view(),
        name="projet-blocages-liste-creer",
    ),
    path(
        "blocages/<uuid:pk>/",
        BlocageDetailView.as_view(),
        name="blocage-detail",
    ),
    path(
        "blocages/<uuid:pk>/prendre-en-charge/",
        BlocagePrendreEnChargeView.as_view(),
        name="blocage-prendre-en-charge",
    ),
    path(
        "blocages/<uuid:pk>/resoudre/",
        BlocageResoudreView.as_view(),
        name="blocage-resoudre",
    ),
]
