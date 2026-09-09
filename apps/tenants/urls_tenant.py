"""Routes du tenant pour l'application tenants."""

from django.urls import path

from apps.tenants.views import EntrepriseView

urlpatterns = [
    path("entreprise/", EntrepriseView.as_view(), name="entreprise-profil"),
]
