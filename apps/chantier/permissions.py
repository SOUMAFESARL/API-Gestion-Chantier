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
    RoleGlobal.DIRECTEUR_PROJET,
    RoleGlobal.CHEF_PROJET,
    RoleGlobal.CONDUCTEUR_TRAVAUX,
    RoleGlobal.CHEF_CHANTIER,
)

ROLES_VALIDATION_CHANTIER = (
    RoleGlobal.ADMIN,
    RoleGlobal.DIRECTEUR_GENERAL,
    RoleGlobal.DIRECTEUR_PROJET,
    RoleGlobal.CHEF_PROJET,
    RoleGlobal.CONDUCTEUR_TRAVAUX,
)


class PeutConsulterRapports(permissions.BasePermission):
    """Vérifie que l'utilisateur peut consulter les rapports de chantier."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if (
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or user.role_global in ROLES_GESTION_CHANTIER
        ):
            return True

        perm = PermissionModule.pour(ModuleChoix.CHANTIER, NiveauAcces.LECTURE)()
        return perm.has_permission(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if (
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or user.role_global in ROLES_DIRECTION
        ):
            return True

        return MembreDuProjet().has_object_permission(request, view, obj)


class PeutRedigerRapports(permissions.BasePermission):
    """Vérifie que l'utilisateur peut créer ou modifier un rapport journalier."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if (
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or user.role_global in (
                RoleGlobal.ADMIN,
                RoleGlobal.DIRECTEUR_GENERAL,
                RoleGlobal.CHEF_CHANTIER,
                RoleGlobal.CONDUCTEUR_TRAVAUX,
                RoleGlobal.CHEF_PROJET,
            )
        ):
            return True

        perm = PermissionModule.pour(ModuleChoix.CHANTIER, NiveauAcces.ECRITURE)()
        return perm.has_permission(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if (
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or user.role_global in ROLES_DIRECTION
        ):
            return True

        return MembreDuProjet().has_object_permission(request, view, obj)


class PeutValiderRapports(permissions.BasePermission):
    """Vérifie que l'utilisateur a autorité pour valider ou rejeter un rapport (CT / CP / DG)."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if (
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or user.role_global in ROLES_VALIDATION_CHANTIER
        ):
            return True

        perm = PermissionModule.pour(ModuleChoix.CHANTIER, NiveauAcces.VALIDATION)()
        return perm.has_permission(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if (
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or user.role_global in ROLES_DIRECTION
        ):
            return True

        # Vérifier l'affectation projet
        from django.apps import apps as registre

        try:
            AffectationProjet = registre.get_model("projets", "AffectationProjet")
            projet_id = MembreDuProjet._extraire_projet_id(obj)
            if not projet_id:
                return False

            affectation = AffectationProjet.objects.filter(
                utilisateur=user, projet_id=projet_id, est_actif=True
            ).first()

            if affectation and (
                affectation.role_projet
                in (
                    RoleProjet.CONDUCTEUR_TRAVAUX,
                    RoleProjet.CHEF_PROJET,
                    RoleProjet.DIRECTEUR_PROJET,
                )
                or user.role_global in ROLES_VALIDATION_CHANTIER
            ):
                return True
        except LookupError:
            pass

        perm = PermissionModule.pour(ModuleChoix.CHANTIER, NiveauAcces.VALIDATION)()
        return perm.has_object_permission(request, view, obj)
