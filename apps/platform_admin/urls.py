from django.urls import path

from apps.platform_admin.views import (
    ChangerPlanClientPlateformeView,
    ClientsPlateformeListView,
    ConnexionAdminView,
    DeconnexionAdminView,
    DeconnexionAssistanceView,
    DemandeReinitialisationAdminView,
    DemarrerAssistanceView,
    EvolutionAbonnementsView,
    FicheClientPlateformeView,
    IndicateursPlateformeView,
    JournalPlateformeListView,
    ListerUtilisateursEntrepriseView,
    ReactiverClientPlateformeView,
    ReinitialisationAdminView,
    RenouvellementAdminView,
    SuspendreClientPlateformeView,
    TendancesIndicateursView,
    VerificationJetonAdminView,
)
from apps.platform_admin.views.inscriptions import (
    ApprouverInscriptionView,
    DemandeInscriptionDetailView,
    DemandesInscriptionView,
    RefuserInscriptionView,
)

app_name = "platform_admin"

urlpatterns = [
    path("admins/inscriptions/", DemandesInscriptionView.as_view(), name="inscriptions-liste"),
    path(
        "admins/inscriptions/<uuid:pk>/",
        DemandeInscriptionDetailView.as_view(),
        name="inscriptions-detail",
    ),
    path(
        "admins/inscriptions/<uuid:pk>/approuver/",
        ApprouverInscriptionView.as_view(),
        name="inscriptions-approuver",
    ),
    path(
        "admins/inscriptions/<uuid:pk>/refuser/",
        RefuserInscriptionView.as_view(),
        name="inscriptions-refuser",
    ),
    # Authentification Super Admin (Control Plane)
    path(
        "admins/connexion/",
        ConnexionAdminView.as_view(),
        name="admins-connexion",
    ),
    path(
        "admins/deconnexion/",
        DeconnexionAdminView.as_view(),
        name="admins-deconnexion",
    ),
    path(
        "admins/token/refresh/",
        RenouvellementAdminView.as_view(),
        name="admins-token-refresh",
    ),
    # Réinitialisation Mot de passe Super Admin
    path(
        "admins/mot-de-passe/demande/",
        DemandeReinitialisationAdminView.as_view(),
        name="admins-mot-de-passe-demande",
    ),
    path(
        "admins/mot-de-passe/verifier/",
        VerificationJetonAdminView.as_view(),
        name="admins-mot-de-passe-verifier",
    ),
    path(
        "admins/mot-de-passe/reinitialiser/",
        ReinitialisationAdminView.as_view(),
        name="admins-mot-de-passe-reinitialiser",
    ),
    # Assistance Super Admin & Impersonation (R-128)
    path(
        "admins/entreprises/<uuid:entreprise_id>/assistance/",
        DemarrerAssistanceView.as_view(),
        name="assistance-demarrer",
    ),
    path(
        "admins/entreprises/<uuid:entreprise_id>/utilisateurs/",
        ListerUtilisateursEntrepriseView.as_view(),
        name="assistance-utilisateurs",
    ),
    path(
        "admins/assistance/deconnexion/",
        DeconnexionAssistanceView.as_view(),
        name="assistance-deconnexion",
    ),
    # Journal de Plateforme
    path(
        "admins/journal-plateforme/",
        JournalPlateformeListView.as_view(),
        name="journal-plateforme-liste",
    ),
    # Tableau de bord d'administration & Indicateurs
    path(
        "admins/indicateurs/",
        IndicateursPlateformeView.as_view(),
        name="admins-indicateurs-plateforme",
    ),
    path(
        "admins/indicateurs/tendances/",
        TendancesIndicateursView.as_view(),
        name="admins-indicateurs-tendances",
    ),
    path(
        "admins/indicateurs/evolution/",
        EvolutionAbonnementsView.as_view(),
        name="admins-indicateurs-evolution",
    ),
    # Gestion Clients & Actions Super Admin
    path(
        "admins/clients/",
        ClientsPlateformeListView.as_view(),
        name="admins-clients-plateforme-liste",
    ),
    path(
        "admins/clients/<uuid:client_id>/",
        FicheClientPlateformeView.as_view(),
        name="admins-clients-plateforme-fiche",
    ),
    path(
        "admins/clients/<uuid:client_id>/suspendre/",
        SuspendreClientPlateformeView.as_view(),
        name="admins-clients-plateforme-suspendre",
    ),
    path(
        "admins/clients/<uuid:client_id>/reactiver/",
        ReactiverClientPlateformeView.as_view(),
        name="admins-clients-plateforme-reactiver",
    ),
    path(
        "admins/clients/<uuid:client_id>/abonnement/",
        ChangerPlanClientPlateformeView.as_view(),
        name="admins-clients-plateforme-abonnement",
    ),
]
