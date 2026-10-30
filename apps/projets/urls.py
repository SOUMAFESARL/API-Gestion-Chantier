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
from apps.projets.views.affectation import (
    CollaborateursAffectablesView,
    ProjetAffectationDetailView,
    ProjetAffectationListCreateView,
    ProjetChefChantierView,
    ProjetRemplacerView,
)
from apps.projets.views.avenants import AvenantDetailView, AvenantDocumentView, ProjetAvenantsView
from apps.projets.views.calendrier import (
    CalendrierEntrepriseView,
    ExceptionCalendrierDetailView,
    ExceptionCalendrierListCreateView,
    SemaineTypeView,
)
from apps.projets.views.decoupage import (
    ElementCloturerView,
    ElementDeplacerView,
    ElementDesactiverView,
    ElementDetaillerView,
    ElementDetailView,
    ElementMesureView,
    ElementPlanifierView,
    ElementReactiverView,
    ElementRouvrirView,
    ElementSuspendreView,
    ListeDetailView,
    ListesView,
    ListeValeursView,
    ModeleDetailView,
    ModelePersonnaliserView,
    ModelesView,
    ProjetArbreView,
    ProjetDecoupageExporterView,
    ProjetDecoupageImporterView,
    ProjetDecoupageView,
    ProjetElementsView,
    ProjetNiveauDetailView,
    ProjetNiveauxInsererView,
    ProjetNiveauxView,
    ProjetTableauVerifierView,
    ValeurListeDetailView,
)
from apps.projets.views.equipe import (
    MainOeuvreDetailView,
    MainOeuvreListCreateView,
    ProjetEquipeAffectationDetailView,
    ProjetEquipeAffectationView,
    ProjetEquipeDetailView,
    ProjetEquipeListCreateView,
    ProjetEquipeMembreDetailView,
    ProjetEquipeMembreListCreateView,
    ProjetEquipeStatistiquesView,
)
from apps.projets.views.referentiels import (
    ReferentielDroitsView,
    ReferentielEntreeView,
    ReferentielListeView,
)
from apps.projets.views.reprogrammation import (
    ElementHistoriqueDatesView,
    ElementReprogrammerView,
    GlobalJournalReportsView,
    MotifReportListCreateView,
    ProjetHistoriqueDatesView,
    ProjetJournalReportsConsolideView,
    ProjetReprogrammerView,
)
from apps.projets.views.statistiques import ProjetStatistiquesView

app_name = "projets"

ORIGINE = r"(?P<origine>PLATEFORME|ENTREPRISE|plateforme|entreprise)"
UUID = r"[0-9a-fA-F-]{36}"

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
    # Découpage : listes de valeurs et modèles (plateforme + entreprise)
    path("decoupage/listes/", ListesView.as_view(), name="decoupage-listes"),
    re_path(
        rf"^decoupage/listes/{ORIGINE}/(?P<pk>{UUID})/$",
        ListeDetailView.as_view(),
        name="decoupage-liste-detail",
    ),
    re_path(
        rf"^decoupage/listes/{ORIGINE}/(?P<pk>{UUID})/valeurs/$",
        ListeValeursView.as_view(),
        name="decoupage-liste-valeurs",
    ),
    path(
        "decoupage/valeurs/<uuid:pk>/",
        ValeurListeDetailView.as_view(),
        name="decoupage-valeur-detail",
    ),
    path("decoupage/modeles/", ModelesView.as_view(), name="decoupage-modeles"),
    path(
        "decoupage/modeles/PLATEFORME/<uuid:pk>/personnaliser/",
        ModelePersonnaliserView.as_view(),
        name="decoupage-modele-personnaliser",
    ),
    re_path(
        rf"^decoupage/modeles/{ORIGINE}/(?P<pk>{UUID})/$",
        ModeleDetailView.as_view(),
        name="decoupage-modele-detail",
    ),
    # Registre de main-d'œuvre de l'entreprise
    path("main-oeuvre/", MainOeuvreListCreateView.as_view(), name="main-oeuvre-liste"),
    path("main-oeuvre/<uuid:pk>/", MainOeuvreDetailView.as_view(), name="main-oeuvre-detail"),
    # Projets
    path("projets/", ProjetListCreateView.as_view(), name="projet-liste-creer"),
    path(
        "projets/journal-reports/",
        GlobalJournalReportsView.as_view(),
        name="projets-journal-reports-global",
    ),
    path("projets/meteo/", MeteoProjetView.as_view(), name="projet-meteo"),
    path("projets/referentiels/villes/", ReferentielVillesView.as_view(), name="projet-villes-ci"),
    path("projets/<uuid:pk>/", ProjetDetailView.as_view(), name="projet-detail"),
    # Découpage d'un projet : tableau de démarrage, arbre, niveaux, cases
    path("projets/<uuid:pk>/decoupage/", ProjetDecoupageView.as_view(), name="projet-decoupage"),
    path("projets/<uuid:pk>/avenants/", ProjetAvenantsView.as_view(), name="projet-avenants"),
    path("avenants/<uuid:pk>/", AvenantDetailView.as_view(), name="avenant-detail"),
    path("avenants/<uuid:pk>/document/", AvenantDocumentView.as_view(), name="avenant-document"),
    path(
        "projets/<uuid:pk>/decoupage/importer/",
        ProjetDecoupageImporterView.as_view(),
        name="projet-decoupage-importer",
    ),
    path(
        "projets/<uuid:pk>/decoupage/exporter/",
        ProjetDecoupageExporterView.as_view(),
        name="projet-decoupage-exporter",
    ),
    path(
        "projets/<uuid:pk>/decoupage/verifier/",
        ProjetTableauVerifierView.as_view(),
        name="projet-decoupage-verifier",
    ),
    path("projets/<uuid:pk>/arbre/", ProjetArbreView.as_view(), name="projet-arbre"),
    path("projets/<uuid:pk>/niveaux/", ProjetNiveauxView.as_view(), name="projet-niveaux"),
    path(
        "projets/<uuid:pk>/niveaux/inserer/",
        ProjetNiveauxInsererView.as_view(),
        name="projet-niveaux-inserer",
    ),
    path(
        "projets/<uuid:pk>/niveaux/<uuid:niveau_id>/",
        ProjetNiveauDetailView.as_view(),
        name="projet-niveau-detail",
    ),
    path("projets/<uuid:pk>/elements/", ProjetElementsView.as_view(), name="projet-elements"),
    path("elements/<uuid:pk>/", ElementDetailView.as_view(), name="element-detail"),
    path("elements/<uuid:pk>/planifier/", ElementPlanifierView.as_view(), name="element-planifier"),
    path(
        "elements/<uuid:pk>/reprogrammer/",
        ElementReprogrammerView.as_view(),
        name="element-reprogrammer",
    ),
    path(
        "elements/<uuid:pk>/historique-dates/",
        ElementHistoriqueDatesView.as_view(),
        name="element-historique-dates",
    ),
    path("elements/<uuid:pk>/deplacer/", ElementDeplacerView.as_view(), name="element-deplacer"),
    path("elements/<uuid:pk>/detailler/", ElementDetaillerView.as_view(), name="element-detailler"),
    path(
        "elements/<uuid:pk>/desactiver/", ElementDesactiverView.as_view(), name="element-desactiver"
    ),
    path("elements/<uuid:pk>/reactiver/", ElementReactiverView.as_view(), name="element-reactiver"),
    path(
        "elements/<uuid:pk>/suspension/", ElementSuspendreView.as_view(), name="element-suspension"
    ),
    path("elements/<uuid:pk>/mesure/", ElementMesureView.as_view(), name="element-mesure"),
    path("elements/<uuid:pk>/cloturer/", ElementCloturerView.as_view(), name="element-cloturer"),
    path("elements/<uuid:pk>/rouvrir/", ElementRouvrirView.as_view(), name="element-rouvrir"),
    # Équipes
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
    # Affectations des collaborateurs (rôle par projet, périmètre)
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
        "projets/<uuid:projet_id>/affectations/remplacer/",
        ProjetRemplacerView.as_view(),
        name="projet-affectations-remplacer",
    ),
    path(
        "projets/<uuid:projet_id>/chef-chantier/",
        ProjetChefChantierView.as_view(),
        name="projet-chef-chantier",
    ),
    path(
        "projets/<uuid:projet_id>/collaborateurs-affectables/",
        CollaborateursAffectablesView.as_view(),
        name="projet-collaborateurs-affectables",
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
