from django.urls import path

from apps.billing.views import (
    AbonnementView,
    CinetPayWebhookView,
    InitierPaiementView,
    PlansCatalogueView,
    StatutPaiementView,
)

app_name = "billing"

urlpatterns = [
    path("abonnement/", AbonnementView.as_view(), name="abonnement"),
    path("plans/", PlansCatalogueView.as_view(), name="plans-catalogue"),
    path("cinetpay/initier/", InitierPaiementView.as_view(), name="cinetpay-initier"),
    path("cinetpay/webhook/", CinetPayWebhookView.as_view(), name="cinetpay-webhook"),
    path(
        "cinetpay/statut/<str:transaction_id>/",
        StatutPaiementView.as_view(),
        name="cinetpay-statut",
    ),
]
