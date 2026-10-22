"""Strict creation form contract, independently of the detail contract."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet

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


@pytest.mark.parametrize("field", ["nom", "ville", "type_projet", "maitre_ouvrage"])
def test_required_fields(formulaire_client, field):
    data = payload()
    data.pop(field)
    assert formulaire_client.post("/api/v1/projets/", data, format="json").status_code == 400
    assert not Projet.objects.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "00000000-0000-0000-0000-000000000001"),
        ("lots", []),
        ("equipe", {}),
        ("client", None),
        ("quartier", "Centre"),
        ("statut", "INVALIDE"),
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


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "00000000-0000-0000-0000-000000000001"),
        ("lots", []),
        ("client", None),
        ("reference", "Autre"),
        ("duree_jours_ouvres", 10),
    ],
)
def test_update_rejects_extra_fields(formulaire_client, method, field, value):
    client = formulaire_client
    created = client.post("/api/v1/projets/", payload(), format="json")
    response = getattr(client, method)(
        created["Location"], {**payload(), field: value}, format="json"
    )
    assert response.status_code == 400
    assert client.get(created["Location"]).data == created.data


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("field", ["date_debut_baseline", "date_fin_baseline"])
def test_baseline_message_and_immutability(formulaire_client, method, field):
    client = formulaire_client
    created = client.post(
        "/api/v1/projets/",
        {
            **payload(),
            "date_debut_prevue": "2026-10-05",
            "date_fin_prevue": "2026-10-09",
        },
        format="json",
    )
    assert created.status_code == 201
    refused = getattr(client, method)(
        created["Location"],
        {
            **payload(),
            field: "2027-01-01",
        },
        format="json",
    )
    assert refused.status_code == 400
    assert "Baseline v0" in str(refused.data)
    projet = Projet.objects.get(reference=created.data["reference"])
    assert projet.date_debut_baseline.isoformat() == "2026-10-05"
    assert projet.date_fin_baseline.isoformat() == "2026-10-09"
    assert client.get(created["Location"]).data == created.data


def test_put_cannot_clear_existing_planning_without_reprogramming(formulaire_client):
    client = formulaire_client
    created = client.post(
        "/api/v1/projets/",
        {
            **payload(),
            "date_debut_prevue": "2026-10-05",
            "date_fin_prevue": "2026-10-09",
        },
        format="json",
    )
    assert created.status_code == 201
    refused = client.put(created["Location"], payload(), format="json")
    assert refused.status_code == 400
    assert "RG-11" in str(refused.data)
    assert client.get(created["Location"]).data == created.data


def test_created_url_is_readable_by_browser_client(formulaire_client):
    created = formulaire_client.post(
        "/api/v1/projets/", payload(), format="json", HTTP_ORIGIN="https://frontend.example"
    )
    assert created.status_code == 201
    exposed = {
        header.strip().lower() for header in created["Access-Control-Expose-Headers"].split(",")
    }
    assert "location" in exposed
    assert formulaire_client.get(created["Location"]).status_code == 200
