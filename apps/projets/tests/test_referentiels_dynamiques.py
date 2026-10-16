"""Référentiels dynamiques : types de projet et noms de lot (arbitrage du 16/10/2026)."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.catalogue.models import ReferentielPlateforme
from apps.core.enums import RoleGlobal, StatutUtilisateur

pytestmark = pytest.mark.django_db

SCHEMA = "demo"
URL_TYPES = "/api/v1/referentiels/types-projet/"
URL_LOTS = "/api/v1/referentiels/lots/"


@pytest.fixture
def client_dg():
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="dg.referentiels@ccd-digital.ci",
            defaults={"is_active": True, "role_global": RoleGlobal.DIRECTEUR_GENERAL},
        )
        user.role_global = RoleGlobal.DIRECTEUR_GENERAL
        user.save()
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def client_admin(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superviseur.ref@ccd-digital.ci").delete()
        admin = Utilisateur.objects.create_superuser(
            email="superviseur.ref@ccd-digital.ci",
            password="MotDePasse12345!",
            nom="Superviseur",
            prenom="Ref",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(HTTP_HOST="localhost")
    client.force_authenticate(admin)
    return client


def test_liste_initiale_vient_de_la_plateforme(client_dg):
    types = client_dg.get(URL_TYPES).json()
    attendu = {"code": "TP_ROUTE", "libelle": "TP — Route", "groupe": ""}
    assert {**attendu, "origine": "PLATEFORME"} in types
    lots = client_dg.get(URL_LOTS).json()
    gros_oeuvre = next(e for e in lots if e["libelle"] == "Gros œuvre")
    assert gros_oeuvre["groupe"] == "Lots architecturaux"
    assert gros_oeuvre["origine"] == "PLATEFORME"


def test_ajout_entreprise_puis_retrait(client_dg):
    rep = client_dg.post(URL_TYPES, {"libelle": "Réhabilitation"}, format="json")
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    assert rep.json() == {
        "code": "REHABILITATION",
        "libelle": "Réhabilitation",
        "groupe": "",
        "origine": "ENTREPRISE",
    }
    assert any(e["code"] == "REHABILITATION" for e in client_dg.get(URL_TYPES).json())

    doublon = client_dg.post(URL_TYPES, {"libelle": "  rehabilitation "}, format="json")
    assert doublon.status_code == status.HTTP_400_BAD_REQUEST

    assert client_dg.delete(f"{URL_TYPES}REHABILITATION/").status_code == status.HTTP_204_NO_CONTENT
    assert not any(e["code"] == "REHABILITATION" for e in client_dg.get(URL_TYPES).json())


def test_entree_plateforme_non_supprimable_par_l_entreprise(client_dg):
    rep = client_dg.delete(f"{URL_TYPES}TP_ROUTE/")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert any(e["code"] == "TP_ROUTE" for e in client_dg.get(URL_TYPES).json())


def test_ajout_plateforme_propage_a_l_entreprise(client_admin, client_dg):
    rep = client_admin.post(
        "/api/v1/admins/referentiels/lots/",
        {"libelle": "Ascenseurs et monte-charges", "groupe": "Lots techniques"},
        format="json",
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    pk = rep.json()["id"]

    lots = client_dg.get(URL_LOTS).json()
    assert any(
        e["libelle"] == "Ascenseurs et monte-charges" and e["origine"] == "PLATEFORME" for e in lots
    )

    assert client_admin.delete(f"/api/v1/admins/referentiels/lots/{pk}/").status_code == 204
    with schema_context(get_public_schema_name()):
        assert not ReferentielPlateforme.objects.filter(pk=pk).exists()


def test_type_projet_hors_liste_refuse(client_dg):
    from rest_framework.exceptions import ValidationError

    from apps.projets.serializers import ProjetCreationSerializer

    serializer = ProjetCreationSerializer()
    with schema_context(SCHEMA):
        assert serializer.validate_type_projet("TP_ROUTE") == "TP_ROUTE"
        with pytest.raises(ValidationError):
            serializer.validate_type_projet("TYPE_INVENTE")
