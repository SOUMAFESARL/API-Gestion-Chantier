from django.urls import path

from apps.platform_admin.views import (
    AdminChangerMotDePasseMoiView,
    AdminModuleAffecterPermissionsView,
    AdminModuleDesactiverView,
    AdminModuleDetailUpdateDeleteView,
    AdminModuleListCreateView,
    AdminModuleReactiverView,
    AdminPermissionAffecterModulesView,
    AdminPermissionDetailUpdateDeleteView,
    AdminPermissionListCreateView,
    AdminPhotoMoiView,
    AdminProfilMoiView,
    ChangerPlanClientPlateformeView,
    ClientsPlateformeListView,
    ComptesAdministrateursListCreateView,
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
    ReactiverCompteAdministrateurView,
    ReinitialisationAdminView,
    RenouvellementAdminView,
    SuspendreClientPlateformeView,
    SuspendreCompteAdministrateurView,
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
    # Gestion Dynamique des Modules (Super Admin)
    path("admin/modules/", AdminModuleListCreateView.as_view(), name="admin-modules-liste-creer"),
    path("admin/modules/<uuid:pk>/", AdminModuleDetailUpdateDeleteView.as_view(), name="admin-modules-detail-modifier-supprimer"),
    path("admin/modules/<uuid:pk>/permissions/", AdminModuleAffecterPermissionsView.as_view(), name="admin-modules-affecter-permissions"),
    path("admin/modules/<uuid:pk>/desactiver/", AdminModuleDesactiverView.as_view(), name="admin-modules-desactiver"),
    path("admin/modules/<uuid:pk>/reactiver/", AdminModuleReactiverView.as_view(), name="admin-modules-reactiver"),
    path("admins/modules/", AdminModuleListCreateView.as_view(), name="admins-modules-liste-creer"),
    path("admins/modules/<uuid:pk>/", AdminModuleDetailUpdateDeleteView.as_view(), name="admins-modules-detail-modifier-supprimer"),
    path("admins/modules/<uuid:pk>/permissions/", AdminModuleAffecterPermissionsView.as_view(), name="admins-modules-affecter-permissions"),
    path("admins/modules/<uuid:pk>/desactiver/", AdminModuleDesactiverView.as_view(), name="admins-modules-desactiver"),
    path("admins/modules/<uuid:pk>/reactiver/", AdminModuleReactiverView.as_view(), name="admins-modules-reactiver"),
    # Gestion Dynamique des Permissions (Super Admin)
    path("admin/permissions/", AdminPermissionListCreateView.as_view(), name="admin-permissions-liste-creer"),
    path("admin/permissions/<uuid:pk>/", AdminPermissionDetailUpdateDeleteView.as_view(), name="admin-permissions-detail-modifier-supprimer"),
    path("admin/permissions/<uuid:pk>/modules/", AdminPermissionAffecterModulesView.as_view(), name="admin-permissions-affecter-modules"),
    path("admins/permissions/", AdminPermissionListCreateView.as_view(), name="admins-permissions-liste-creer"),
    path("admins/permissions/<uuid:pk>/", AdminPermissionDetailUpdateDeleteView.as_view(), name="admins-permissions-detail-modifier-supprimer"),
    path("admins/permissions/<uuid:pk>/modules/", AdminPermissionAffecterModulesView.as_view(), name="admins-permissions-affecter-modules"),
    # Gestion des Comptes Administrateurs (Super Admin)
    path("admins/comptes/", ComptesAdministrateursListCreateView.as_view(), name="admins-comptes-liste-creer"),
    path("admins/comptes/<uuid:pk>/suspendre/", SuspendreCompteAdministrateurView.as_view(), name="admins-comptes-suspendre"),
    path("admins/comptes/<uuid:pk>/reactiver/", ReactiverCompteAdministrateurView.as_view(), name="admins-comptes-reactiver"),
    # Profil Super Admin connecté
    path("admins/moi/", AdminProfilMoiView.as_view(), name="admins-moi"),
    path("admins/moi/photo/", AdminPhotoMoiView.as_view(), name="admins-moi-photo"),
    path("admins/moi/mot-de-passe/", AdminChangerMotDePasseMoiView.as_view(), name="admins-moi-mot-de-passe"),
    # Alias compatibles Frontend Direct
    path("clients/<uuid:client_id>/suspendre/", SuspendreClientPlateformeView.as_view(), name="clients-plateforme-suspendre-alias"),
    path("clients/<uuid:client_id>/reactiver/", ReactiverClientPlateformeView.as_view(), name="clients-plateforme-reactiver-alias"),
    path("clients/<uuid:client_id>/abonnement/", ChangerPlanClientPlateformeView.as_view(), name="clients-plateforme-abonnement-alias"),
    path("indicateurs/", IndicateursPlateformeView.as_view(), name="indicateurs-plateforme-alias"),
    path("indicateurs/tendances/", TendancesIndicateursView.as_view(), name="indicateurs-tendances-alias"),
    path("indicateurs/evolution/", EvolutionAbonnementsView.as_view(), name="indicateurs-evolution-alias"),
]
