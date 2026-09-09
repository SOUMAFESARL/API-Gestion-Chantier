"""Routes de l'inscription — **domaine de la plateforme uniquement**.

Au moment de l'inscription, le client n'a pas encore de sous-domaine : ces cinq
routes sont montées par `config/urls_public.py`, jamais par `urls_tenant.py`.
"""

from django.urls import path

from apps.tenants.views import (
    ActivationView,
    DepotInscriptionView,
    EtatProvisionnementView,
    RenvoiActivationView,
    VerificationJetonInscriptionView,
)

app_name = "tenants"

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
