"""Strict creation form contract, independently of the detail contract."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet
from apps.projets.serializers.swagger import CHAMPS_FORMULAIRE

pytestmark = pytest.mark.django_db


@pytest.fixture
def formulaire_client(schema_demo):
    user = Utilisateur.objects.create_user(
        email="formulaire.strict@demo.ci",
        password="Test12345!",
        nom="Direction",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    return client


def payload():
    return {
        "nom": "Palmiers",
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Man",
        "maitre_ouvrage": "sglaq",
    }


def test_creation_and_persistence(formulaire_client):
    data = {
        **payload(),
        "maitre_oeuvre": "Cabinet",
        "description": "Construction",
        "date_debut_prevue": "2026-10-05",
        "date_fin_prevue": "2026-10-09",
        "budget_initial_montant": 48500000000,
    }
    response = formulaire_client.post("/api/v1/projets/", data, format="json")
    assert response.status_code == 201, response.data
    assert set(response.data) == set(CHAMPS_FORMULAIRE)
    assert response.data["duree_jours_ouvres"] == 5
    for key, value in data.items():
        assert response.data[key] == value
    projet = Projet.objects.get(reference=response.data["reference"])
    assert projet.chef_projet_id is None
    assert not projet.lots.exists() and not projet.affectations.exists()


def test_optional_fields(formulaire_client):
    response = formulaire_client.post("/api/v1/projets/", payload(), format="json")
    assert response.status_code == 201, response.data
    assert response.data["duree_jours_ouvres"] is None
    assert response.data["budget_initial_montant"] is None


@pytest.mark.parametrize("field", ["nom", "ville", "type_projet", "maitre_ouvrage"])
def test_required_fields(formulaire_client, field):
    data = payload()
    data.pop(field)
    assert formulaire_client.post("/api/v1/projets/", data, format="json").status_code == 400
    assert not Projet.objects.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("lots", []),
        ("equipe", {}),
        ("client", None),
        ("quartier", "Centre"),
        ("statut", "EN_ATTENTE"),
        ("chef_projet_id", None),
        ("inconnu", True),
        ("reference", "PRJ-2026-010"),
        ("duree_jours_ouvres", 5),
        ("budget_initial_montant", -1),
        ("type_projet", "invalide"),
    ],
)
def test_invalid_fields_no_creation(formulaire_client, field, value):
    response = formulaire_client.post(
        "/api/v1/projets/", {**payload(), field: value}, format="json"
    )
    assert response.status_code == 400, response.data
    assert not Projet.objects.exists()


def test_reversed_dates(formulaire_client):
    response = formulaire_client.post(
        "/api/v1/projets/",
        {
            **payload(),
            "date_debut_prevue": "2026-10-09",
            "date_fin_prevue": "2026-10-05",
        },
        format="json",
    )
    assert response.status_code == 400
    assert not Projet.objects.exists()


def test_full_crud_form_only(formulaire_client):
    client = formulaire_client
    created = client.post("/api/v1/projets/", payload(), format="json")
    assert created.status_code == 201, created.data
    url = created["Location"]
    detail = client.get(url)
    assert detail.status_code == 200
    assert set(detail.data) == set(CHAMPS_FORMULAIRE)
    listed = client.get("/api/v1/projets/")
    assert listed.status_code == 200
    assert all(set(row) == set(CHAMPS_FORMULAIRE) for row in listed.data)
    updated = client.patch(url, {"description": "Phase 2"}, format="json")
    assert updated.status_code == 200
    assert updated.data["nom"] == payload()["nom"]
    assert updated.data["description"] == "Phase 2"
    assert set(updated.data) == set(CHAMPS_FORMULAIRE)
    assert client.put(url, {"nom": "Incomplet"}, format="json").status_code == 400
    replaced = client.put(url, {**payload(), "nom": "Phase 3"}, format="json")
    assert replaced.status_code == 200, replaced.data
    assert replaced.data["description"] == ""
    assert set(replaced.data) == set(CHAMPS_FORMULAIRE)
    assert replaced.data["reference"] == created.data["reference"]
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize(
    "field,value",
    [("lots", []), ("client", None), ("reference", "Autre"), ("duree_jours_ouvres", 10)],
)
def test_update_rejects_extra_fields(formulaire_client, method, field, value):
    client = formulaire_client
    created = client.post("/api/v1/projets/", payload(), format="json")
    response = getattr(client, method)(
        created["Location"], {**payload(), field: value}, format="json"
    )
    assert response.status_code == 400
    assert client.get(created["Location"]).data == created.data
