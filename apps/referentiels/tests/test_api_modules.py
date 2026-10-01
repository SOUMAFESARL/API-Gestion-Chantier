"""Tests pour l'API du catalogue des modules (GET /api/v1/modules/)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import (
    MODULES_DETAILS,
    ModuleChoix,
    NiveauAcces,
    RoleGlobal,
    StatutUtilisateur,
)

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def collaborateur_user(db):
    """Collaborateur standard authentifié."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="collab.modules@demo.ci",
            defaults={
                "nom": "Collaborateur",
                "prenom": "Test",
                "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.CONDUCTEUR_TRAVAUX
        user.is_owner = False
        user.save()
        return user


@pytest.mark.django_db
class TestApiCatalogueModules:
    """Suite de tests pour GET /api/v1/modules/."""

    def test_get_modules_anonyme_refuse(self, client_tenant):
        """Un appel anonyme doit être rejeté en 401 Unauthorized."""
        response = client_tenant.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_modules_authentifie_succes(self, client_tenant, collaborateur_user):
        """Un utilisateur connecté reçoit une réponse HTTP 200."""
        client_tenant.force_authenticate(user=collaborateur_user)
        response = client_tenant.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_200_OK

    def test_get_modules_structure_exacte(self, client_tenant, collaborateur_user):
        """Vérifie que la liste contient exactement les 5 modules ordonnés avec toutes leurs métadonnées."""
        client_tenant.force_authenticate(user=collaborateur_user)
        response = client_tenant.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data) == 5

        # Ordre strict attendu
        codes_attendus = ["projets", "chantier", "ged", "pilotage", "tiers"]
        codes_reçus = [m["code"] for m in data]
        assert codes_reçus == codes_attendus

        # Vérification des champs de chaque module
        for item in data:
            assert "code" in item
            assert "libelle" in item
            assert "description" in item
            assert "ordre" in item
            assert "icone" in item
            assert "permissions" in item
            assert "permissions_codes" in item
            assert "niveaux_supportes" in item
            assert item["code"] in ModuleChoix.values
            assert item["description"] == MODULES_DETAILS[item["code"]]["description"]
            assert item["icone"] == MODULES_DETAILS[item["code"]]["icone"]

    def test_get_modules_niveaux_supportes(self, client_tenant, collaborateur_user):
        """Vérifie que chaque module inclut les 4 niveaux d'accès RBAC (0 à 3)."""
        client_tenant.force_authenticate(user=collaborateur_user)
        response = client_tenant.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        for item in data:
            niveaux = item["niveaux_supportes"]
            assert len(niveaux) == 4
            valeurs_niveaux = [n["niveau"] for n in niveaux]
            assert valeurs_niveaux == [0, 1, 2, 3]

            codes_niveaux = [n["code"] for n in niveaux]
            assert codes_niveaux == ["AUCUN", "LECTURE", "ECRITURE", "VALIDATION"]

            for n in niveaux:
                assert n["libelle"] != ""

    def test_get_modules_permissions_dynamiques(self, client_tenant, collaborateur_user):
        """Vérifie que chaque module inclut la liste dynamique de ses autorisations granulaires."""
        client_tenant.force_authenticate(user=collaborateur_user)
        response = client_tenant.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        for item in data:
            assert "permissions" in item
            assert isinstance(item["permissions"], list)
            assert len(item["permissions"]) > 0
            codes = item["permissions_codes"]
            assert isinstance(codes, list)
            for p in item["permissions"]:
                assert "id" in p
                assert "code" in p
                assert "libelle" in p
