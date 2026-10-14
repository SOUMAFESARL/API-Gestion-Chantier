"""Permissions DRF pour le module platform_admin."""

from django.db import connection
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from apps.core.enums import RoleGlobal

MESSAGE_SUPERVISEUR = _("Seul un superviseur de la plateforme peut effectuer cette action.")


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


def exiger_superviseur(request) -> None:
    """Le SUPPORT lit le back-office ; seul le superviseur le modifie.

    Appelée en tête de chaque méthode d'écriture réservée : un contrôle par méthode, et non
    une classe de permission, parce que la même vue sert souvent la lecture (ouverte au
    SUPPORT) et l'écriture (fermée).
    """
    if not getattr(request.user, "is_superuser", False):
        raise PermissionDenied(MESSAGE_SUPERVISEUR)
