from django.urls import path

from .views import SignerBonPaiementView

app_name = "finance"

urlpatterns = [
    path(
        "finance/bons-paiement/<uuid:pk>/signer/",
        SignerBonPaiementView.as_view(),
        name="signer-bon-paiement",
    ),
]
