"""Permissions DRF pour le module platform_admin."""

from django.db import connection
from django_tenants.utils import get_public_schema_name
from rest_framework.permissions import BasePermission

from apps.core.enums import RoleGlobal


class EstSuperAdminPlateforme(BasePermission):
    """
    Vérifie que l'utilisateur est authentifié et possède les droits Super Admin / Staff éditeur.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        schema_courant = getattr(connection, "schema_name", "public")
        public_schema = get_public_schema_name()

        # Doit être authentifié dans le schéma public ou avoir un statut staff
        est_schema_autorise = (schema_courant == public_schema) or getattr(user, "is_staff", False)
        if not est_schema_autorise:
            return False

        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "role_global", None) == RoleGlobal.ADMIN
        )
