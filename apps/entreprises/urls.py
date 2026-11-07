"""Routes de l'inscription — publiques : l'entreprise n'existe pas encore (contrat T-021)."""

from django.urls import path

from apps.entreprises.views import (
    ActivationView,
    DepotInscriptionView,
    EtatProvisionnementView,
    RenvoiActivationView,
    VerificationJetonInscriptionView,
)

app_name = "entreprises"

urlpatterns = [
    path("inscription/", DepotInscriptionView.as_view(), name="inscription"),
    path("inscription/renvoyer/", RenvoiActivationView.as_view(), name="inscription-renvoyer"),
    path(
        "inscription/verifier/",
        VerificationJetonInscriptionView.as_view(),
        name="inscription-verifier",
    ),
    path("inscription/activer/", ActivationView.as_view(), name="inscription-activer"),
    path(
        "inscription/etat/<uuid:suivi>/",
        EtatProvisionnementView.as_view(),
        name="inscription-etat",
    ),
]
