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
