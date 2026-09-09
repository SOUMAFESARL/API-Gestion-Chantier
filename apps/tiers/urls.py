"""Routes pour l'application tiers."""

from django.urls import path

from apps.tiers.views import TiersDetailView, TiersListCreateView

app_name = "tiers"

urlpatterns = [
    path("tiers/", TiersListCreateView.as_view(), name="tiers-liste-creer"),
    path("tiers/<uuid:pk>/", TiersDetailView.as_view(), name="tiers-detail"),
]
