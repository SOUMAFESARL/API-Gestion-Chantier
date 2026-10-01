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
from apps.projets.views.activite import (
    ActiviteDetailView,
    LotActiviteListCreateView,
)
from apps.projets.views.affectation import (
    ProjetAffectationDetailView,
    ProjetAffectationListCreateView,
)
from apps.projets.views.contexte_creation import ContexteCreationProjetView
from apps.projets.views.reprogrammation import (
    ActiviteHistoriqueDatesView,
    ActiviteReprogrammerView,
    GlobalJournalReportsView,
    LotHistoriqueDatesView,
    LotReprogrammerView,
    MotifReportListCreateView,
    ProjetHistoriqueDatesView,
    ProjetJournalReportsConsolideView,
    ProjetReprogrammerView,
)

app_name = "projets"

urlpatterns = [
    # Référentiel des motifs de report
    path(
        "referentiels/motifs-report/",
        MotifReportListCreateView.as_view(),
        name="motifs-report-liste-creer",
    ),

    # Projets
    path("projets/", ProjetListCreateView.as_view(), name="projet-liste-creer"),
    path(
        "projets/journal-reports/",
        GlobalJournalReportsView.as_view(),
        name="projets-journal-reports-global",
    ),
    path(
        "projets/contexte-creation/",
        ContexteCreationProjetView.as_view(),
        name="projet-contexte-creation",
    ),
    path("projets/meteo/", MeteoProjetView.as_view(), name="projet-meteo"),
    path("projets/referentiels/villes/", ReferentielVillesView.as_view(), name="projet-villes-ci"),
    path("projets/<uuid:pk>/", ProjetDetailView.as_view(), name="projet-detail"),
    path(
        "projets/<uuid:pk>/permissions-roles/",
        ProjetPermissionsRolesView.as_view(),
        name="projet-permissions-roles",
    ),
    path(
        "projets/<uuid:pk>/reprogrammer/",
        ProjetReprogrammerView.as_view(),
        name="projet-reprogrammer",
    ),
    path(
        "projets/<uuid:pk>/historique-dates/",
        ProjetHistoriqueDatesView.as_view(),
        name="projet-historique-dates",
    ),
    path(
        "projets/<uuid:pk>/journal-reports/",
        ProjetJournalReportsConsolideView.as_view(),
        name="projet-journal-reports-consolide",
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

    # Lots
    path(
        "lots/<uuid:pk>/reprogrammer/",
        LotReprogrammerView.as_view(),
        name="lot-reprogrammer",
    ),
    path(
        "lots/<uuid:pk>/historique-dates/",
        LotHistoriqueDatesView.as_view(),
        name="lot-historique-dates",
    ),
    path(
        "lots/<uuid:lot_id>/activites/",
        LotActiviteListCreateView.as_view(),
        name="lot-activites-liste-creer",
    ),

    # Activités
    path(
        "activites/<uuid:pk>/",
        ActiviteDetailView.as_view(),
        name="activite-detail",
    ),
    path(
        "activites/<uuid:pk>/reprogrammer/",
        ActiviteReprogrammerView.as_view(),
        name="activite-reprogrammer",
    ),
    path(
        "activites/<uuid:pk>/historique-dates/",
        ActiviteHistoriqueDatesView.as_view(),
        name="activite-historique-dates",
    ),

    # Tableau de bord
    path("tableau-de-bord/", TableauDeBordView.as_view(), name="tableau-de-bord"),
]
