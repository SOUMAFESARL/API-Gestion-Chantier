"""Tests d'acceptation de l'administration des rôles (Règle B-05)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role
from apps.catalogue.models import CataloguePermission

SCHEMA_TEST = "demo"

pytestmark = pytest.mark.django_db


def test_b05_cocher_administration_refuse_role_personnalise(client_dg):
    """[B-05] L'API refuse (HTTP 400) d'attribuer une permission d'administration à un rôle personnalisé."""
    payload = {
        "code": "PERSO_ADMIN_TEST",
        "libelle": "Personnalisé Tentative Admin",
        "description": "Test de refus règle B-05",
        "permissions": ["administration.roles_gerer"],
    }
    rep = client_dg.post("/api/v1/roles/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST


def test_b05_cocher_administration_refuse_role_systeme(client_dg):
    """[B-05] L'API refuse (HTTP 400) d'ajouter une permission d'administration sur un rôle système."""
    with schema_context(SCHEMA_TEST):
        role_cp = Role.objects.filter(code="CP", supprime_le__isnull=True).first()
        assert role_cp is not None, "Rôle CP manquant"
        cp_id = role_cp.id

    payload = {
        "permissions": ["administration.entreprise_modifier"],
    }
    rep = client_dg.patch(f"/api/v1/roles/{cp_id}/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST


def test_b05_cocher_permission_ordinaire_accepte(client_dg):
    """[B-05] L'attribution d'une permission métier autorisée (non réservée administration) est acceptée."""
    payload = {
        "code": "PERSO_METIER_OK",
        "libelle": "Personnalisé Métier Valide",
        "description": "Test d'acceptation règle B-05",
        "permissions_modules": {
            "chantier": 2,
        },
    }
    rep = client_dg.post("/api/v1/roles/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
