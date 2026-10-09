"""Un incident email après provisionnement conserve un compte utilisable."""

from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.services.authentification import authentifier
from apps.billing.models import Plan
from apps.tenants.models import DemandeInscription
from apps.tenants.services.inscription import deposer, provisionner


@pytest.mark.django_db
def test_smtp_failure_keeps_activation_ready_and_password_valid(schema_demo):
    password = "Chantier2026!"
    with schema_context("public"):
        Plan.objects.get_or_create(code=Plan.Code.PRO, defaults={"libelle": "Pro"})
        demande = deposer(
            identifiant=None, raison_sociale="Activation test",
            pays="CI", email="activation.smtp@example.ci",
        )
        demande.slug_reserve = "demo"
        demande.statut = DemandeInscription.Statut.PROVISIONNEMENT
        demande.mot_de_passe_transitoire = make_password(password)
        demande.save()
        with patch(
            "apps.tenants.services.inscription._envoyer_espace_pret",
            side_effect=RuntimeError("SMTP indisponible"),
        ):
            provisionner(demande.pk)
        demande.refresh_from_db()
        assert demande.statut == DemandeInscription.Statut.ACTIVEE
        assert demande.entreprise_id is not None
        assert demande.mot_de_passe_transitoire == ""
    with schema_context("demo"):
        user = authentifier(demande.email, password)
        assert user.is_owner
    response = APIClient(HTTP_HOST="localhost").get(
        f"/api/v1/inscription/etat/{demande.pk}/"
    )
    assert response.status_code == 200
    assert response.data["statut"] == "PRET"
