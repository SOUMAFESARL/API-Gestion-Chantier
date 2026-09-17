from django.urls import path

from apps.platform_admin.views import (
    DeconnexionAssistanceView,
    DemarrerAssistanceView,
    JournalPlateformeListView,
    ListerUtilisateursEntrepriseView,
)

app_name = "platform_admin"

urlpatterns = [
    path(
        "super-admin/entreprises/<uuid:entreprise_id>/assistance/",
        DemarrerAssistanceView.as_view(),
        name="assistance-demarrer",
    ),
    path(
        "super-admin/entreprises/<uuid:entreprise_id>/utilisateurs/",
        ListerUtilisateursEntrepriseView.as_view(),
        name="assistance-utilisateurs",
    ),
    path(
        "super-admin/assistance/deconnexion/",
        DeconnexionAssistanceView.as_view(),
        name="assistance-deconnexion",
    ),
    path(
        "super-admin/journal-plateforme/",
        JournalPlateformeListView.as_view(),
        name="journal-plateforme-liste",
    ),
]
