"""Tests de la déconnexion et de la révocation de session (DEV-3.6)."""

import pytest
from django.core.cache import cache
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"
URL_CONNEXION = "/api/v1/auth/token/"
URL_RENOUVELLEMENT = "/api/v1/auth/token/refresh/"
URL_DECONNEXION = "/api/v1/auth/deconnexion/"
MOT_DE_PASSE = "MotDePasse1!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture(autouse=True)
def cache_propre():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def utilisateur(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="deconnexion@btp.ci").delete()
        yield Utilisateur.objects.create_user(
            email="deconnexion@btp.ci",
            password=MOT_DE_PASSE,
            nom="Touré",
            prenom="Amina",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )


def connecter(client):
    return client.post(
        URL_CONNEXION,
        {"email": "deconnexion@btp.ci", "mot_de_passe": MOT_DE_PASSE, "origine": "WEB"},
        format="json",
    )


@pytest.mark.django_db
def test_deconnexion_revoque_jeton_refresh(client, utilisateur):
    """Après déconnexion, le jeton de renouvellement est révoqué et inutilisable."""
    rep_conn = connecter(client)
    assert rep_conn.status_code == status.HTTP_200_OK
    refresh = rep_conn.data["refresh"]

    # Déconnexion
    rep_dec = client.post(URL_DECONNEXION, {"refresh": refresh}, format="json")
    assert rep_dec.status_code == status.HTTP_200_OK

    # Tentative de renouvellement avec le refresh révoqué -> 401
    rep_renouv = client.post(URL_RENOUVELLEMENT, {"refresh": refresh}, format="json")
    assert rep_renouv.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_deconnexion_idempotente_et_tolerante(client):
    """La déconnexion réussit même sans corps ou avec un jeton invalide."""
    rep1 = client.post(URL_DECONNEXION, {}, format="json")
    assert rep1.status_code == status.HTTP_200_OK

    rep2 = client.post(URL_DECONNEXION, {"refresh": "invalide"}, format="json")
    assert rep2.status_code == status.HTTP_200_OK
