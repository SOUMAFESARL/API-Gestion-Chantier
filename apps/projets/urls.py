"""Routes pour l'application projets."""

from django.urls import path, re_path

from apps.projets.views import (
    AlerteRetardListView,
    AlerteRetardResoudreView,
    ArretChantierDetailView,
    MeteoProjetView,
    ProjetArretChantierListCreateView,
    ProjetDetailView,
    ProjetListCreateView,
    ProjetPlanningView,
    ProjetSanteApercuView,
    ProjetSanteDetailView,
    ProjetSanteHistoriqueView,
    ReferentielVillesView,
    TableauDeBordView,
)
from apps.projets.views.activite import (
    ActiviteActivationView,
    ActiviteAvancementHistoriqueView,
    ActiviteAvancementView,
    ActiviteDetailView,
    LotActiviteListCreateView,
)
from apps.projets.views.affectation import (
    CollaborateursAffectablesView,
    ProjetAffectationDetailView,
    ProjetAffectationListCreateView,
)
from apps.projets.views.calendrier import (
    CalendrierEntrepriseView,
    ExceptionCalendrierDetailView,
    ExceptionCalendrierListCreateView,
    SemaineTypeView,
)
from apps.projets.views.equipe import (
    ProjetEquipeAffectationDetailView,
    ProjetEquipeAffectationView,
    ProjetEquipeDetailView,
    ProjetEquipeListCreateView,
    ProjetEquipeMembreDetailView,
    ProjetEquipeMembreListCreateView,
    ProjetEquipeStatistiquesView,
)
from apps.projets.views.lot import (
    LotActivationView,
    LotDetailView,
    ProjetLotImportView,
    ProjetLotListCreateView,
    ProjetLotModeleView,
)
from apps.projets.views.referentiels import (
    ReferentielDroitsView,
    ReferentielEntreeView,
    ReferentielListeView,
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
    path(
        "projets/motifs-report/",
        MotifReportListCreateView.as_view(),
        name="projets-motifs-report-alias",
    ),
    # Référentiels dynamiques : types de projet et noms de lot (plateforme + entreprise)
    path("referentiels/droits/", ReferentielDroitsView.as_view(), name="referentiel-droits"),
    re_path(
        r"^referentiels/(?P<categorie>types-projet|lots|modes-execution)/$",
        ReferentielListeView.as_view(),
        name="referentiel-liste",
    ),
    re_path(
        r"^referentiels/(?P<categorie>types-projet|lots|modes-execution)/(?P<code>[A-Za-z0-9_]+)/$",
        ReferentielEntreeView.as_view(),
        name="referentiel-entree",
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
        "projets/<uuid:pk>/equipes/<uuid:equipe_id>/membres/",
        ProjetEquipeMembreListCreateView.as_view(),
        name="projet-equipe-membres",
    ),
    path(
        "projets/<uuid:pk>/equipes/<uuid:equipe_id>/membres/<uuid:membre_id>/",
        ProjetEquipeMembreDetailView.as_view(),
        name="projet-equipe-membre-detail",
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
    path("projets/meteo/", MeteoProjetView.as_view(), name="projet-meteo"),
    path("projets/referentiels/villes/", ReferentielVillesView.as_view(), name="projet-villes-ci"),
    path("projets/<uuid:pk>/", ProjetDetailView.as_view(), name="projet-detail"),
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
        "projets/<uuid:pk>/planning/",
        ProjetPlanningView.as_view(),
        name="projet-planning",
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
    path(
        "projets/<uuid:projet_id>/collaborateurs-affectables/",
        CollaborateursAffectablesView.as_view(),
        name="projet-collaborateurs-affectables",
    ),
    # Lots
    path("lots/<uuid:pk>/", LotDetailView.as_view(), name="lot-detail"),
    path("lots/<uuid:pk>/activation/", LotActivationView.as_view(), name="lot-activation"),
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
        "activites/<uuid:pk>/activation/",
        ActiviteActivationView.as_view(),
        name="activite-activation",
    ),
    path(
        "activites/<uuid:pk>/avancement/",
        ActiviteAvancementView.as_view(),
        name="activite-avancement",
    ),
    path(
        "activites/<uuid:pk>/avancement/historique/",
        ActiviteAvancementHistoriqueView.as_view(),
        name="activite-avancement-historique",
    ),
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
    # Alertes de retard (SFD F3 §5.4 & Erratum E-3)
    path(
        "alertes-retard/",
        AlerteRetardListView.as_view(),
        name="alerte-retard-liste",
    ),
    path(
        "alertes-retard/<uuid:pk>/resoudre/",
        AlerteRetardResoudreView.as_view(),
        name="alerte-retard-resoudre",
    ),
    # Calendrier d'entreprise (SFD F3 §6 & Erratum E-4)
    path("calendrier/", CalendrierEntrepriseView.as_view(), name="calendrier-entreprise"),
    path(
        "calendrier/semaine-type/",
        SemaineTypeView.as_view(),
        name="calendrier-semaine-type",
    ),
    path(
        "calendrier/exceptions/",
        ExceptionCalendrierListCreateView.as_view(),
        name="calendrier-exceptions",
    ),
    path(
        "calendrier/exceptions/<uuid:pk>/",
        ExceptionCalendrierDetailView.as_view(),
        name="calendrier-exception-detail",
    ),
]
