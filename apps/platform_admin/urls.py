from django.urls import path

from apps.platform_admin.views import (
    ConnexionAdminView,
    DeconnexionAdminView,
    DeconnexionAssistanceView,
    DemarrerAssistanceView,
    JournalPlateformeListView,
    ListerUtilisateursEntrepriseView,
    RenouvellementAdminView,
)

app_name = "platform_admin"

urlpatterns = [
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
]
