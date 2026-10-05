"""Tests de non-régression pour la transition et l'API profil (Règle G-02)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_TEST = "demo"

pytestmark = pytest.mark.django_db


def test_g02_profil_conserve_role_global_habilitations_permissions(client_tenant):
    """[G-02] GET /api/v1/auth/profil/ continue d'exposer role_global, habilitations et permissions."""
    with schema_context(SCHEMA_TEST):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="user.g02.test@demo.ci",
            defaults={
                "nom": "Transition",
                "prenom": "G02",
                "role_global": RoleGlobal.CHEF_PROJET,
                "statut": StatutUtilisateur.ACTIF,
            },
        )

    client_tenant.force_authenticate(user=user)
    rep = client_tenant.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK

    data = rep.data
    assert "role_global" in data, "La clé 'role_global' doit être conservée pour compatibilité"
    assert "habilitations" in data, "La clé 'habilitations' doit être conservée pour le frontend"
    assert "permissions" in data, "La clé 'permissions' doit être présente"
    assert isinstance(data["habilitations"], dict)
    assert isinstance(data["permissions"], list)
