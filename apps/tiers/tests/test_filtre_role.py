"""`GET /tiers/?role=` : les listes maître d'ouvrage et maître d'œuvre du formulaire de projet."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleTiersChoix

HOTE = "demo.localhost"
SCHEMA = "demo"


@pytest.fixture
def client_dg(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="dg.tiers@ccd-digital.ci",
            defaults={"is_active": True, "role_global": RoleGlobal.DIRECTEUR_GENERAL},
        )
        user.role_global = RoleGlobal.DIRECTEUR_GENERAL
        user.save()
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_filtre_par_role_et_creation_maitre_oeuvre(client_dg):
    for nom, role in (("Cabinet MOE Test", "MAITRE_OEUVRE"), ("Client MOA Test", "CLIENT_MOA")):
        reponse = client_dg.post(
            "/api/v1/tiers/",
            {"raison_sociale": nom, "telephone": "+2250700000000", "roles": [role]},
            format="json",
        )
        assert reponse.status_code == status.HTTP_201_CREATED, reponse.data

    moe = client_dg.get("/api/v1/tiers/", {"role": RoleTiersChoix.MAITRE_OEUVRE})
    noms_moe = {t["raison_sociale"] for t in moe.data}
    assert "Cabinet MOE Test" in noms_moe
    assert "Client MOA Test" not in noms_moe

    tous = client_dg.get("/api/v1/tiers/")
    noms = {t["raison_sociale"] for t in tous.data}
    assert {"Cabinet MOE Test", "Client MOA Test"} <= noms
