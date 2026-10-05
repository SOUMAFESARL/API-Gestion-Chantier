"""Fixtures d'acceptation pour le Lot 1 (REGISTRE, catalogue, permissions effectives)."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_TEST = "demo"
HOTE_TENANT = "demo.localhost"
HOTE_PUBLIC = "localhost"


@pytest.fixture(autouse=True)
def initialiser_catalogue_test(db):
    """Garantit que le catalogue public et les rôles de base sont initialisés pour les tests."""
    from django.core.management import call_command
    with schema_context(get_public_schema_name()):
        call_command("synchroniser_catalogue_permissions")
    with schema_context(SCHEMA_TEST):
        from apps.accounts.models import Role
        if not Role.objects.filter(supprime_le__isnull=True).exists():
            from apps.accounts.services.roles import initialiser_roles_par_defaut
            initialiser_roles_par_defaut()


@pytest.fixture
def client_tenant():
    """Client API configuré sur l'hôte du tenant de test."""
    return APIClient(HTTP_HOST=HOTE_TENANT)


@pytest.fixture
def client_public():
    """Client API configuré sur l'hôte de la plateforme (schéma public)."""
    return APIClient(HTTP_HOST=HOTE_PUBLIC)


@pytest.fixture
def super_admin(db):
    """Crée et retourne un Super Administrateur dans le schéma public."""
    with schema_context(get_public_schema_name()):
        admin, _ = Utilisateur.tous_objets.get_or_create(
            email="superadmin.lot1@ccd-digital.ci",
            defaults={
                "nom": "Super",
                "prenom": "Admin",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        return admin


@pytest.fixture
def client_super_admin(client_public, super_admin):
    """Client authentifié en tant que Super Admin sur le schéma public."""
    client_public.force_authenticate(user=super_admin)
    return client_public


@pytest.fixture
def dg_user(db):
    """Crée et retourne le Directeur Général du tenant de test."""
    with schema_context(SCHEMA_TEST):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.acceptation.lot1@demo.ci",
            defaults={
                "nom": "Directeur",
                "prenom": "General",
                "role_global": RoleGlobal.DIRECTEUR_GENERAL,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": True,
            },
        )
        user.is_owner = True
        user.save()
        return user


@pytest.fixture
def client_dg(client_tenant, dg_user):
    """Client authentifié en tant que Directeur Général du tenant."""
    client_tenant.force_authenticate(user=dg_user)
    return client_tenant


def creer_utilisateur_role(code_role: str, email: str = None) -> Utilisateur:
    """Helper pour créer un utilisateur avec un rôle système ou personnalisé donné."""
    email = email or f"user.{code_role.lower()}.lot1@demo.ci"
    with schema_context(SCHEMA_TEST):
        role_obj = Role.objects.filter(code=code_role, supprime_le__isnull=True).first()
        user, _ = Utilisateur.tous_objets.get_or_create(
            email=email,
            defaults={
                "nom": f"Nom_{code_role}",
                "prenom": f"Prenom_{code_role}",
                "role_global": code_role if hasattr(RoleGlobal, code_role) else RoleGlobal.VISITEUR,
                "role_personnalise": role_obj if role_obj and not role_obj.est_systeme else None,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        if role_obj:
            if not role_obj.est_systeme:
                user.role_personnalise = role_obj
            else:
                user.role_global = code_role
            user.save()
        return user
