"""Fabriques et helpers pour les tests d'acceptation du Lot 2."""

from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_TEST = "demo"
HOTE_TENANT = "demo.localhost"
HOTE_PUBLIC = "localhost"


def client_pour(utilisateur, host: str = HOTE_TENANT) -> APIClient:
    """Retourne un APIClient authentifié pour l'utilisateur sur l'hôte spécifié."""
    client = APIClient(HTTP_HOST=host)
    if utilisateur:
        client.force_authenticate(user=utilisateur)
    return client


def obtenir_dg() -> Utilisateur:
    """Retourne le Directeur Général du tenant de test (demo)."""
    with schema_context(SCHEMA_TEST):
        role_dg = Role.objects.filter(code="DG", supprime_le__isnull=True).first()
        defaults = {
            "nom": "Directeur",
            "prenom": "General",
            "role_global": getattr(RoleGlobal, "DIRECTEUR_GENERAL", "DG"),
            "statut": StatutUtilisateur.ACTIF,
            "is_owner": True,
        }
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.lot2@demo.ci",
            defaults=defaults,
        )
        user.is_owner = True
        if role_dg and hasattr(user, "role_id"):
            user.role = role_dg
        if role_dg and hasattr(user, "role_personnalise_id"):
            user.role_personnalise = role_dg
        user.save()
        return user


def obtenir_super_admin() -> Utilisateur:
    """Retourne le Super Administrateur de la plateforme dans le schéma public."""
    with schema_context(get_public_schema_name()):
        admin, _ = Utilisateur.tous_objets.get_or_create(
            email="superadmin.lot2@ccd-digital.ci",
            defaults={
                "nom": "Super",
                "prenom": "Admin",
                "role_global": getattr(RoleGlobal, "ADMIN", "AD"),
                "statut": StatutUtilisateur.ACTIF,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        return admin


def client_super_admin() -> APIClient:
    """Retourne un client authentifié en Super Admin sur le schéma public."""
    admin = obtenir_super_admin()
    return client_pour(admin, host=HOTE_PUBLIC)


def utilisateur_avec_role(code_role: str, email: str = None) -> Utilisateur:
    """Crée ou récupère un utilisateur avec le rôle spécifié dans le schéma tenant."""
    email = email or f"user.{code_role.lower()}.lot2@demo.ci"
    with schema_context(SCHEMA_TEST):
        role_obj = Role.objects.filter(code=code_role, supprime_le__isnull=True).first()
        defaults = {
            "nom": f"Nom_{code_role}",
            "prenom": f"Prenom_{code_role}",
            "statut": StatutUtilisateur.ACTIF,
        }
        if hasattr(RoleGlobal, code_role):
            defaults["role_global"] = getattr(RoleGlobal, code_role)
        else:
            defaults["role_global"] = RoleGlobal.VISITEUR

        user, _ = Utilisateur.tous_objets.get_or_create(
            email=email,
            defaults=defaults,
        )
        if role_obj:
            if hasattr(user, "role_id"):
                user.role = role_obj
            if not role_obj.est_systeme and hasattr(user, "role_personnalise_id"):
                user.role_personnalise = role_obj
            user.save()
        return user


def creer_role_personnalise(code: str, libelle: str, portee: str = "PROJET") -> Role:
    """Crée un rôle personnalisé dans le schéma de test avec la portée demandée."""
    with schema_context(SCHEMA_TEST):
        role, _ = Role.objects.update_or_create(
            code=code.upper(),
            defaults={
                "libelle": libelle,
                "est_systeme": False,
                "est_actif": True,
            },
        )
        if hasattr(role, "portee"):
            role.portee = portee
            role.save()
        return role


def obtenir_role(code: str) -> Role:
    """Récupère un rôle actif par son code dans le schéma de test."""
    with schema_context(SCHEMA_TEST):
        return Role.objects.filter(code=code, supprime_le__isnull=True).first()
