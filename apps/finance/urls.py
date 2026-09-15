from django.urls import path

from .views import (
    BonPaiementDetailView,
    BonPaiementListCreateView,
    SignerBonPaiementView,
)

app_name = "finance"

urlpatterns = [
    path(
        "finance/bons-paiement/",
        BonPaiementListCreateView.as_view(),
        name="bon-paiement-liste-creer",
    ),
    path(
        "finance/bons-paiement/<uuid:pk>/",
        BonPaiementDetailView.as_view(),
        name="bon-paiement-detail",
    ),
    path(
        "finance/bons-paiement/<uuid:pk>/signer/",
        SignerBonPaiementView.as_view(),
        name="signer-bon-paiement",
    ),
]
