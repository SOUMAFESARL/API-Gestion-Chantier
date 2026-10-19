"""Rôles système gérés par le super admin — `/api/v1/admins/roles-systeme/`."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.catalogue.models import ModeleRole, ModeleRoleModule
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
        },
        format="json",
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    pk = rep.json()["id"]
    assert rep.json()["portee"] == "PROJET"
    assert rep.json()["modules"] == []
    assert "protege" not in rep.json()

    role = _role_demo("QSE")
    assert role is not None and role.est_systeme
    assert role.libelle == "Responsable QSE"
    assert role.portee == "PROJET"
    with schema_context(SCHEMA):
        rmps = list(RoleModulePermission.objects.filter(role=role))
        assert RoleModulePermission.objects.filter(role=role).exists()
        assert sum(rmp.permissions_catalogue.count() for rmp in rmps) == 0
    with schema_context(get_public_schema_name()):
        assert not ModeleRoleModule.objects.filter(
            modele_role_id=pk, supprime_le__isnull=True
        ).exists()

    # Une modification qui envoie portee ou modules ne les change pas
    rep = superviseur_client.patch(
        f"{URL}{pk}/",
        {
            "libelle": "Responsable HSE",
            "portee": "ENTREPRISE",
            "modules": ["projets"],
        },
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content
    assert rep.json()["libelle"] == "Responsable HSE"
    assert rep.json()["portee"] == "PROJET"
    assert rep.json()["modules"] == []
    assert "protege" not in rep.json()
    assert _role_demo("QSE").libelle == "Responsable HSE"
    assert _role_demo("QSE").portee == "PROJET"

    rep = superviseur_client.delete(f"{URL}{pk}/")
    assert rep.status_code == status.HTTP_200_OK, rep.content
    role = _role_demo("QSE")
    assert role is not None, "le rôle reste dans l'entreprise"
    assert role.est_systeme is False, "il devient personnalisé"
    with schema_context(get_public_schema_name()):
        assert not ModeleRole.objects.filter(code="QSE").exists()


def test_role_du_socle_garde_ses_modules_apres_modification(superviseur_client):
    with schema_context(get_public_schema_name()):
        modele = ModeleRole.objects.get(code="CT")
        modules_avant = sorted(
            m.module_code for m in modele.modules_plafonds.all() if m.supprime_le is None
        )
        assert len(modules_avant) > 0

    rep = superviseur_client.patch(
        f"{URL}{modele.id}/",
        {"libelle": "Conducteur de Travaux Principal"},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content
    assert rep.json()["libelle"] == "Conducteur de Travaux Principal"
    assert rep.json()["modules"] == modules_avant

    with schema_context(get_public_schema_name()):
        modele.refresh_from_db()
        modules_apres = sorted(
            m.module_code for m in modele.modules_plafonds.all() if m.supprime_le is None
        )
        assert modules_apres == modules_avant
        assert modele.libelle == "Conducteur de Travaux Principal"


def test_role_du_socle_supprimable(superviseur_client):
    with schema_context(get_public_schema_name()):
        modele = ModeleRole.objects.get(code="CT")
    rep = superviseur_client.delete(f"{URL}{modele.id}/")
    assert rep.status_code == status.HTTP_200_OK, rep.content
    role = _role_demo("CT")
    assert role is not None, "le rôle reste dans l'entreprise"
    assert role.est_systeme is False, "il devient personnalisé"
    with schema_context(get_public_schema_name()):
        assert not ModeleRole.objects.filter(code="CT").exists()
    liste = superviseur_client.get(URL).json()
    assert not any(r["code"] == "CT" for r in liste)
    assert all("protege" not in r for r in liste)


def test_role_dg_non_supprimable(superviseur_client):
    with schema_context(get_public_schema_name()):
        modele = ModeleRole.objects.get(code="DG")
    rep = superviseur_client.delete(f"{URL}{modele.id}/")
    assert rep.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    message_attendu = (
        "Le rôle DG ne se supprime pas : chaque entreprise en a besoin pour son administrateur."
    )
    assert rep.json()["erreur"]["message"] == message_attendu


def test_code_en_double_refuse(superviseur_client):
    rep = superviseur_client.post(
        URL, {"code": "CT", "libelle": "Doublon"}, format="json"
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
