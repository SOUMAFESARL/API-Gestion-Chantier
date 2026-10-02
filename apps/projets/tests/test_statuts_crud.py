"""Statuts explicites et autorisation limitée au changement de statut."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet
from apps.projets.tests.test_creation_formulaire_strict import payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def formulaire_client(schema_demo):
    user = Utilisateur.objects.create_user(
        email="statuts.direction@demo.ci", password="Test12345!", nom="Direction",
        role_global=RoleGlobal.ADMIN, statut=StatutUtilisateur.ACTIF,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    return client


@pytest.mark.parametrize("statut", StatutProjet.values)
def test_creation_and_roundtrip_status(formulaire_client, statut):
    response = formulaire_client.post(
        "/api/v1/projets/", {**payload(), "statut": statut}, format="json"
    )
    assert response.status_code == 201, response.data
    assert response.data["statut"] == statut
    url = response["Location"]
    assert formulaire_client.get(url).data["statut"] == statut
    assert formulaire_client.get("/api/v1/projets/").data[0]["statut"] == statut
    replaced = formulaire_client.put(url, payload(), format="json")
    assert replaced.status_code == 200, replaced.data
    assert replaced.data["statut"] == statut


def test_member_status_only_permissions(formulaire_client):
    created = formulaire_client.post("/api/v1/projets/", payload(), format="json")
    assert created.data["statut"] == StatutProjet.EN_ATTENTE
    projet = Projet.objects.get(pk=created.data["id"])
    user = Utilisateur.objects.create_user(
        email="statuts.visiteur@demo.ci", password="Test12345!",
        nom="Visiteur", role_global=RoleGlobal.VISITEUR, statut=StatutUtilisateur.ACTIF,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    url = created["Location"]
    assert client.patch(url, {"statut": "SUSPENDU"}, format="json").status_code == 403
    affectation = AffectationProjet.objects.create(
        utilisateur=user, projet=projet, role_projet=RoleProjet.VISITEUR,
    )
    for statut in ("SUSPENDU", "BLOQUE", "DESACTIVE", "RESILIE", "EN_COURS"):
        result = client.patch(url, {"statut": statut}, format="json")
        assert result.status_code == 200, result.data
        projet.refresh_from_db()
        assert result.data["statut"] == projet.statut == statut
    assert client.patch(url, {"statut": "INVALIDE"}, format="json").status_code == 400
    assert client.patch(
        url, {"statut": "SUSPENDU", "nom": "Interdit"}, format="json"
    ).status_code == 403
    projet.refresh_from_db()
    assert projet.statut == "EN_COURS"
    affectation.est_actif = False
    affectation.save(update_fields=["est_actif"])
    assert client.patch(url, {"statut": "BLOQUE"}, format="json").status_code == 403
    client.force_authenticate(user=None)
    assert client.patch(url, {"statut": "BLOQUE"}, format="json").status_code in (401, 403)
