"""Permissions DRF pour le module platform_admin."""

from django.utils.translation import gettext_lazy as _
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

        # D9, R-8 : le personnel de l'éditeur partage la table `utilisateur` avec les comptes des
        # entreprises. Il se reconnaît à son entreprise nulle — et à rien d'autre : sous
        # django-tenants, c'était le schéma `public` qui le désignait, et un administrateur
        # d'entreprise (`AD`) passerait sinon la condition de rôle ci-dessous.
        if getattr(user, "entreprise_id", None) is not None:
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
