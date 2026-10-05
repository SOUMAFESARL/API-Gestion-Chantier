"""Permissions DRF propres au module « chantier » — rapports journaliers.

Contrôle d'accès à deux niveaux (Socle Commun §2.3) :
- Niveau 1 : Rôle global et permissions du module (CHANTIER).
- Niveau 2 : Affectation au projet spécifique.
"""

from rest_framework import permissions

from apps.core.enums import ModuleChoix, NiveauAcces, RoleGlobal, RoleProjet
from apps.core.permissions import MembreDuProjet, PermissionModule

__all__ = [
    "PeutConsulterRapports",
    "PeutRedigerRapports",
    "PeutValiderRapports",
]

ROLES_DIRECTION = (
    RoleGlobal.ADMIN,
    RoleGlobal.DIRECTEUR_GENERAL,
)

ROLES_GESTION_CHANTIER = (
    RoleGlobal.ADMIN,
    RoleGlobal.DIRECTEUR_GENERAL,
    RoleGlobal.CHEF_PROJET,
    RoleGlobal.CONDUCTEUR_TRAVAUX,
    RoleGlobal.CHEF_CHANTIER,
)

ROLES_VALIDATION_CHANTIER = (
    RoleGlobal.ADMIN,
    RoleGlobal.DIRECTEUR_GENERAL,
    RoleGlobal.CHEF_PROJET,
    RoleGlobal.CONDUCTEUR_TRAVAUX,
)


class PeutConsulterRapports(permissions.BasePermission):
    """Vérifie que l'utilisateur peut consulter les rapports de chantier."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        from apps.core.droits import a_permission

        return a_permission(request.user, "chantier.lire", request=request)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        from apps.core.droits import a_permission

        if a_permission(request.user, "projets.voir_tous", request=request):
            return True

        return MembreDuProjet().has_object_permission(request, view, obj)


class PeutRedigerRapports(permissions.BasePermission):
    """Vérifie que l'utilisateur peut créer ou modifier un rapport journalier."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        from apps.core.droits import a_permission

        return a_permission(request.user, "chantier.rediger", request=request)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        from apps.core.droits import a_permission

        if a_permission(request.user, "projets.voir_tous", request=request):
            return True

        return MembreDuProjet().has_object_permission(request, view, obj)


class PeutValiderRapports(permissions.BasePermission):
    """Vérifie que l'utilisateur a autorité pour valider ou rejeter un rapport."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        from apps.core.droits import a_permission

        return a_permission(request.user, "chantier.valider", request=request)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        from apps.core.droits import a_permission

        if a_permission(request.user, "projets.voir_tous", request=request):
            return True

        return MembreDuProjet().has_object_permission(request, view, obj)
