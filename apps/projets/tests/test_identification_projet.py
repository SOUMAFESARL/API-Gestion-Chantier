"""Création depuis le formulaire d'identification, avant planning et équipe."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet

pytestmark = pytest.mark.django_db


@pytest.fixture
def direction(schema_demo):
    user = Utilisateur.objects.create_user(
        email="identification@demo.ci",
        password="Test12345!",
        nom="Direction",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(user)
    return client, user


def formulaire():
    return {
        "nom": "Immeuble Les Palmiers R+5",
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Abidjan",
        "maitre_ouvrage": "Entreprise cliente",
        "maitre_oeuvre": "Cabinet études",
    }


def test_cycle_identification_sans_planning_ni_equipe(direction):
    client, user = direction
    response = client.post("/api/v1/projets/", formulaire(), format="json")
    assert response.status_code == 201, response.data
    projet = Projet.objects.get(pk=response.data["id"])
    assert projet.cree_par_id == user.pk
    assert projet.chef_projet_id is None
    assert projet.date_debut_prevue is None and projet.date_fin_prevue is None
    assert projet.budget_initial_montant is None
    assert not projet.affectations.exists()
    assert response.data["entreprise"]["schema_name"] == "demo"
    assert response.data["reference"].startswith("PRJ-")
    url = f"/api/v1/projets/{projet.pk}/"
    assert client.get(url).status_code == 200
    assert any(p["id"] == str(projet.pk) for p in client.get("/api/v1/projets/").data)
    assert client.patch(url, {"nom": "Phase 2"}, format="json").status_code == 200
    assert (
        client.patch(
            url,
            {
                "date_debut_prevue": "2026-10-01",
                "date_fin_prevue": "2026-12-31",
            },
            format="json",
        ).status_code
        == 200
    )
    assert client.patch(url, {"date_fin_prevue": "2026-09-01"}, format="json").status_code == 400
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


@pytest.mark.parametrize(
    "champ,valeur",
    [("nom", " "), ("ville", ""), ("maitre_ouvrage", ""), ("type_projet", "inconnu")],
)
def test_identification_invalide(direction, champ, valeur):
    client, _ = direction
    data = formulaire()
    data[champ] = valeur
    assert client.post("/api/v1/projets/", data, format="json").status_code == 400
    assert not Projet.objects.exists()


def test_creation_anonyme_interdite(direction):
    client, _ = direction
    client.force_authenticate(None)
    assert client.post("/api/v1/projets/", formulaire(), format="json").status_code == 401


def test_reference_ne_reutilise_pas_projet_supprime(direction):
    client, _ = direction
    premiere = client.post("/api/v1/projets/", formulaire(), format="json")
    assert premiere.status_code == 201
    assert client.delete(f"/api/v1/projets/{premiere.data['id']}/").status_code == 204
    seconde = client.post("/api/v1/projets/", formulaire(), format="json")
    assert seconde.status_code == 201
    assert premiere.data["reference"] != seconde.data["reference"]


def test_connexion_jwt_puis_creation_sur_domaine_public(direction):
    _, user = direction
    client = APIClient(HTTP_HOST="localhost")
    login = client.post(
        "/api/v1/auth/token/",
        {
            "email": user.email,
            "mot_de_passe": "Test12345!",
            "origine": "WEB",
        },
        format="json",
    )
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    response = client.post("/api/v1/projets/", formulaire(), format="json")
    assert response.status_code == 201, response.data
    assert response.data["entreprise"]["schema_name"] == "demo"
    assert response.data["cree_par"]["id"] == str(user.pk)


def test_tableau_de_bord_sans_responsables(direction, monkeypatch):
    from apps.projets.views import tableau_de_bord

    client, _ = direction
    monkeypatch.setattr(tableau_de_bord, "obtenir_meteo", lambda *a, **k: {})
    response = client.post("/api/v1/projets/", formulaire(), format="json")
    assert response.status_code == 201
    assert client.get("/api/v1/tableau-de-bord/").status_code == 200
