"""Rôles système gérés par le super admin — `/api/v1/admins/roles-systeme/` (arbitrage du 16/10/2026)."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.catalogue.models import ModeleRole
from apps.core.enums import RoleGlobal, StatutUtilisateur

pytestmark = pytest.mark.django_db

HOTE = "localhost"
SCHEMA = "demo"
URL = "/api/v1/admins/roles-systeme/"


@pytest.fixture
def superviseur_client(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superviseur.roles@ccd-digital.ci").delete()
        superviseur = Utilisateur.objects.create_superuser(
            email="superviseur.roles@ccd-digital.ci",
            password="MotDePasse12345!",
            nom="Superviseur",
            prenom="Roles",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(HTTP_HOST=HOTE)
    client.force_authenticate(superviseur)
    return client


def _role_demo(code: str) -> Role | None:
    with schema_context(SCHEMA):
        return Role.objects.filter(code__iexact=code).first()


def test_cycle_creer_modifier_supprimer(superviseur_client):
    rep = superviseur_client.post(
        URL,
        {
            "code": "QSE",
            "libelle": "Responsable QSE",
            "description": "Qualité, sécurité, environnement",
            "portee": "ENTREPRISE",
            "modules": ["projets"],
        },
        format="json",
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    pk = rep.json()["id"]
    assert rep.json()["modules"] == ["projets"]
    assert rep.json()["protege"] is False

    role = _role_demo("QSE")
    assert role is not None and role.est_systeme
    assert role.libelle == "Responsable QSE"

    rep = superviseur_client.patch(f"{URL}{pk}/", {"libelle": "Responsable HSE"}, format="json")
    assert rep.status_code == status.HTTP_200_OK, rep.content
    assert _role_demo("QSE").libelle == "Responsable HSE"

    rep = superviseur_client.delete(f"{URL}{pk}/")
    assert rep.status_code == status.HTTP_200_OK, rep.content
    role = _role_demo("QSE")
    assert role is not None, "le rôle reste dans l'entreprise"
    assert role.est_systeme is False, "il devient personnalisé"
    with schema_context(get_public_schema_name()):
        assert not ModeleRole.objects.filter(code="QSE").exists()


def test_role_du_socle_non_supprimable(superviseur_client):
    with schema_context(get_public_schema_name()):
        modele = ModeleRole.objects.get(code="CT")
    rep = superviseur_client.delete(f"{URL}{modele.id}/")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    liste = superviseur_client.get(URL).json()
    assert next(r for r in liste if r["code"] == "CT")["protege"] is True


def test_code_en_double_refuse(superviseur_client):
    rep = superviseur_client.post(
        URL, {"code": "CT", "libelle": "Doublon", "modules": []}, format="json"
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
