"""Swagger présente le journal même avant l'authentification du tenant."""

import pytest
from django.urls import resolve
from rest_framework.test import APIRequestFactory


@pytest.mark.parametrize("urlconf", ["config.urls_public", "config.urls_tenant"])
def test_schema_servi_contient_le_journal_sans_connexion(urlconf):
    request = APIRequestFactory().get("/api/v1/schema/", HTTP_ACCEPT="application/json")
    response = resolve("/api/v1/schema/", urlconf=urlconf).func(request)
    assert response.status_code == 200
    paths = response.data["paths"]
    assert set(paths["/api/v1/chantier/rapports/"]) == {"get", "post"}
    assert set(paths["/api/v1/chantier/rapports/{id}/"]) == {"get", "patch", "delete"}
    assert "get" in paths["/api/v1/chantier/rapports/preparation/"]
    for action in ("soumettre", "valider", "approuver", "rejeter"):
        assert "post" in paths[f"/api/v1/chantier/rapports/{{id}}/{action}/"]
    assert "post" in paths["/api/v1/projets/"]
    assert "requestBody" not in paths["/api/v1/admins/comptes/{id}/suspendre/"]["post"]
    fields = response.data["components"]["schemas"]["AdminMotDePasseRequest"]["properties"]
    assert {"ancien_mot_de_passe", "nouveau_mot_de_passe"} == set(fields)
