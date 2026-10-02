from django.urls import path

from apps.billing.views import (
    AbonnementView,
    AnnulerPaiementView,
    CinetPayWebhookView,
    InitierPaiementView,
    PlansCatalogueView,
    StatutPaiementView,
)
from apps.billing.views.expiration import NotificationsExpirationView
from apps.billing.views.facture import FactureDetailView, FactureListeView, FacturePDFView

app_name = "billing"

urlpatterns = [
    path(
        "abonnement/notifications/",
        NotificationsExpirationView.as_view(),
        name="notifications-expiration",
    ),
    path("factures/", FactureListeView.as_view(), name="factures"),
    path("factures/<uuid:pk>/", FactureDetailView.as_view(), name="facture-detail"),
    path("factures/<uuid:pk>/pdf/", FacturePDFView.as_view(), name="facture-pdf"),
    path("abonnement/", AbonnementView.as_view(), name="abonnement"),
    path("plans/", PlansCatalogueView.as_view(), name="plans-catalogue"),
    path("cinetpay/initier/", InitierPaiementView.as_view(), name="cinetpay-initier"),
    path("cinetpay/annuler/", AnnulerPaiementView.as_view(), name="cinetpay-annuler"),
    path("cinetpay/webhook/", CinetPayWebhookView.as_view(), name="cinetpay-webhook"),
    path(
        "billing/cinetpay/webhook/",
        CinetPayWebhookView.as_view(),
        name="billing-cinetpay-webhook",
    ),
    path(
        "cinetpay/statut/<str:transaction_id>/",
        StatutPaiementView.as_view(),
        name="cinetpay-statut",
    ),
]
