"""Routes pour l'application projets."""

from django.urls import path

from apps.projets.views import (
    ArretChantierDetailView,
    MeteoProjetView,
    ProjetArretChantierListCreateView,
    ProjetDetailView,
    ProjetListCreateView,
    ProjetPermissionsRolesView,
    ProjetSanteApercuView,
    ProjetSanteDetailView,
    ProjetSanteHistoriqueView,
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
from apps.projets.views.equipe import (
    ProjetEquipeAffectationDetailView,
    ProjetEquipeAffectationView,
    ProjetEquipeDetailView,
    ProjetEquipeListCreateView,
    ProjetEquipeStatistiquesView,
)
from apps.projets.views.lot import (
    ProjetLotImportView,
    ProjetLotListCreateView,
    ProjetLotModeleView,
)
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
from apps.projets.views.statistiques import ProjetStatistiquesView

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
    path("projets/<uuid:pk>/equipes/", ProjetEquipeListCreateView.as_view(), name="projet-equipes"),
    path(
        "projets/<uuid:pk>/equipes/statistiques/",
        ProjetEquipeStatistiquesView.as_view(),
        name="projet-equipes-statistiques",
    ),
    path(
        "projets/<uuid:pk>/equipes/affectations/",
        ProjetEquipeAffectationView.as_view(),
        name="projet-equipes-affectations",
    ),
    path(
        "projets/<uuid:pk>/equipes/affectations/<uuid:affectation_id>/",
        ProjetEquipeAffectationDetailView.as_view(),
        name="projet-equipe-affectation-detail",
    ),
    path(
        "projets/<uuid:pk>/equipes/<uuid:equipe_id>/",
        ProjetEquipeDetailView.as_view(),
        name="projet-equipe-detail",
    ),
    path(
        "projets/<uuid:pk>/statistiques/",
        ProjetStatistiquesView.as_view(),
        name="projet-statistiques",
    ),
    path("projets/<uuid:pk>/lots/", ProjetLotListCreateView.as_view(), name="projet-lots"),
    path(
        "projets/<uuid:pk>/lots/import/", ProjetLotImportView.as_view(), name="projet-lots-import"
    ),
    path(
        "projets/<uuid:pk>/lots/modele/", ProjetLotModeleView.as_view(), name="projet-lots-modele"
    ),
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
    # Santé du projet
    path(
        "projets/<uuid:pk>/sante/",
        ProjetSanteApercuView.as_view(),
        name="projet-sante-apercu",
    ),
    path(
        "projets/<uuid:pk>/sante/historique/",
        ProjetSanteHistoriqueView.as_view(),
        name="projet-sante-historique",
    ),
    path(
        "projets/<uuid:pk>/sante/detail/",
        ProjetSanteDetailView.as_view(),
        name="projet-sante-detail",
    ),
    # Arrêts de chantier
    path(
        "projets/<uuid:projet_id>/arrets-chantier/",
        ProjetArretChantierListCreateView.as_view(),
        name="projet-arrets-chantier-liste-creer",
    ),
    path(
        "arrets-chantier/<uuid:pk>/",
        ArretChantierDetailView.as_view(),
        name="arret-chantier-detail",
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
