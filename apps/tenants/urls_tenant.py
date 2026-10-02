"""Routes du tenant pour l'application tenants."""

from django.urls import path

from apps.tenants.views import ConfigurationEntrepriseView, EntrepriseView

urlpatterns = [
    path("entreprise/", EntrepriseView.as_view(), name="entreprise-profil"),
    path(
        "parametres/configuration/",
        ConfigurationEntrepriseView.as_view(),
        name="parametres-configuration",
    ),
]
