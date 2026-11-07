"""Routes de l'entreprise active : son profil, ses documents, sa configuration."""

from django.urls import path

from apps.projets.views.parametres_documents import ParametresDocumentsView
from apps.entreprises.views import ConfigurationEntrepriseView, EntrepriseView

urlpatterns = [
    path("entreprise/", EntrepriseView.as_view(), name="entreprise-profil"),
    path(
        "entreprise/documents/",
        ParametresDocumentsView.as_view(),
        name="entreprise-documents",
    ),
    path(
        "parametres/configuration/",
        ConfigurationEntrepriseView.as_view(),
        name="parametres-configuration",
    ),
]
