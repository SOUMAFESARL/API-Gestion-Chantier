"""Dates réelles facultatives et cohérence lors des mises à jour partielles."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal

pytestmark = pytest.mark.django_db


def test_real_dates_crud(schema_demo):
    user = Utilisateur.objects.create_user(
        email="dates.reelles@demo.ci", password="Test12345!", nom="Direction",
        role_global=RoleGlobal.ADMIN,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    data = {
        "nom": "Dates", "ville": "Man", "maitre_ouvrage": "Client",
        "type_projet": "BATIMENT_RESIDENTIEL",
    }
    created = client.post("/api/v1/projets/", data, format="json")
    assert created.status_code == 201, created.data
    assert created.data["date_debut_reelle"] is None
    assert created.data["date_fin_reelle"] is None
    url = created["Location"]
    assert client.patch(url, {"date_debut_reelle": "2026-10-02"}, format="json").status_code == 200
    assert client.patch(url, {"date_fin_reelle": "2026-10-01"}, format="json").status_code == 400
    updated = client.patch(url, {"date_fin_reelle": "2026-10-02"}, format="json")
    assert updated.status_code == 200
    assert updated.data["date_fin_reelle"] == "2026-10-02"
    assert client.patch(url, {"date_debut_reelle": "2026-10-03"}, format="json").status_code == 400
    replaced = client.put(url, data, format="json")
    assert replaced.status_code == 200
    assert replaced.data["date_debut_reelle"] == "2026-10-02"
    assert client.get(url).data["date_fin_reelle"] == "2026-10-02"
    assert client.get("/api/v1/projets/").data[0]["date_debut_reelle"] == "2026-10-02"
    cleared = client.patch(url, {
        "date_debut_reelle": None, "date_fin_reelle": None,
    }, format="json")
    assert cleared.status_code == 200
    assert cleared.data["date_debut_reelle"] is None
    invalid = client.post("/api/v1/projets/", {
        **data, "date_debut_reelle": "2026-10-03", "date_fin_reelle": "2026-10-02",
    }, format="json")
    assert invalid.status_code == 400
