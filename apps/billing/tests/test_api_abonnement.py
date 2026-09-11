"""Tests pour l'endpoint GET /api/v1/abonnement/."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Plan
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.abo@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.abo@demo.ci",
            password="MotDePasse1!",
            nom="Kouassi",
            prenom="Jean",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        yield admin


@pytest.mark.django_db
def test_consulter_abonnement_tenant(client_tenant, admin_user):
    """Un utilisateur authentifié peut consulter l'abonnement de son tenant."""
    client_tenant.force_authenticate(user=admin_user)
    url = "/api/v1/abonnement/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["statut"] == Abonnement.Statut.ESSAI
    assert data["plan"]["code"] in [Plan.Code.MAITRE_OEUVRE, Plan.Code.PRO]
    assert data["jours_essai_restants"] == 14
    assert data["est_expire"] is False
    assert data["lecture_seule"] is False


@pytest.mark.django_db
def test_abonnement_anonyme_refuse(client_tenant):
    """Une requête non authentifiée est rejetée (401)."""
    url = "/api/v1/abonnement/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
