"""Restant dynamique et santé non inventée dans les réponses CRUD."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal
from apps.projets.models import Activite, Lot
from apps.projets.services.indicateurs import calculer_sante

pytestmark = pytest.mark.django_db


def test_remaining_from_activities(schema_demo):
    user = Utilisateur.objects.create_user(
        email="indicateurs@demo.ci", password="Test12345!", nom="Direction",
        role_global=RoleGlobal.ADMIN,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    created = client.post("/api/v1/projets/", {
        "nom": "Indicateurs", "ville": "Man", "maitre_ouvrage": "Client",
        "type_projet": "BATIMENT_RESIDENTIEL",
    }, format="json")
    assert created.status_code == 201, created.data
    assert created.data["avancement_reel"] == 100
    assert created.data["indice_sante"] is None
    url = created["Location"]
    lot = Lot.objects.create(projet_id=created.data["id"], code="L1", libelle="Lot")
    activity = Activite.objects.create(
        lot=lot, libelle="Travaux", quantite_prevue=100, quantite_realisee=25,
        date_debut_prevue=date(2026, 10, 1), date_fin_prevue=date(2026, 10, 30),
    )
    response = client.patch(url, {"statut": "EN_COURS"}, format="json")
    assert response.data["avancement_reel"] == 75
    assert client.get("/api/v1/projets/").data[0]["avancement_reel"] == 75
    activity.quantite_realisee = 150
    activity.save()
    assert client.get(url).data["avancement_reel"] == 0
    activity.est_actif = False
    activity.save()
    assert client.get(url).data["avancement_reel"] == 100
    response = client.patch(url, {"statut": "TERMINE"}, format="json")
    assert response.data["avancement_reel"] == 0
    assert client.patch(url, {"avancement_reel": 20}, format="json").status_code == 400


@pytest.mark.parametrize("restant,budget,depenses,expected", [
    (75, 1000, 250, 100), (75, 1000, 500, 75), (75, 1000, 1500, 0),
    (100, None, 0, None), (100, 0, 0, None), (100, 1000, None, None),
])
def test_health_balance(restant, budget, depenses, expected):
    assert calculer_sante(restant, budget, depenses) == expected
