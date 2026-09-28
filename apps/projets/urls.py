"""Routes pour l'application projets."""

from django.urls import path

from apps.projets.views import (
    MeteoProjetView,
    ProjetDetailView,
    ProjetListCreateView,
    ProjetPermissionsRolesView,
    ReferentielVillesView,
    TableauDeBordView,
)

from apps.projets.views.affectation import (
    ProjetAffectationDetailView,
    ProjetAffectationListCreateView,
)

app_name = "projets"

urlpatterns = [
    path("projets/", ProjetListCreateView.as_view(), name="projet-liste-creer"),
    path("projets/meteo/", MeteoProjetView.as_view(), name="projet-meteo"),
    path("projets/referentiels/villes/", ReferentielVillesView.as_view(), name="projet-villes-ci"),
    path("projets/<uuid:pk>/", ProjetDetailView.as_view(), name="projet-detail"),
    path(
        "projets/<uuid:pk>/permissions-roles/",
        ProjetPermissionsRolesView.as_view(),
        name="projet-permissions-roles",
    ),
    path(
        "projets/<uuid:projet_id>/affectations/",
        ProjetAffectationListCreateView.as_view(),
        name="projet-affectations-liste",
    ),
    path(
        "projets/<uuid:projet_id>/affectations/<uuid:pk>/",
        ProjetAffectationDetailView.as_view(),
        name="projet-affectation-detail",
    ),
    path("tableau-de-bord/", TableauDeBordView.as_view(), name="tableau-de-bord"),
]

