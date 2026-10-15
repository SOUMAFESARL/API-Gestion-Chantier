"""Permissions DRF propres au module."""

from rest_framework.permissions import BasePermission

from apps.core.enums import RoleProjet
from apps.core.permissions import GardePermissionProjet


class PeutRetirerDuProjet(BasePermission):
    """Retirer quelqu'un d'un chantier : qui peut affecter (DG, AD, CP affecté), et le CT affecté.

    Le CT n'a pas `projets.affecter_membres` (Annexe 1, tests d'acceptation) :
    il ne fait pas entrer, mais il peut faire sortir quelqu'un de son chantier.
    """

    message = "Vous n'avez pas les droits nécessaires pour cette action."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        from apps.core.droits import a_permission, est_administrateur, est_dg

        if user.is_superuser or est_dg(user) or est_administrateur(user):
            return True

        if a_permission(user, "projets.affecter_membres", request=request):
            return True

        # Le CT peut tenter un retrait s'il est affecté comme CT sur ce projet
        projet_id = view.kwargs.get("projet_id") or view.kwargs.get("pk")
        if projet_id:
            from apps.projets.models import AffectationProjet, Projet

            if AffectationProjet.objects.filter(
                projet_id=projet_id,
                utilisateur=user,
                role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
                est_actif=True,
                supprime_le__isnull=True,
            ).exists() or Projet.objects.filter(
                pk=projet_id,
                conducteur_travaux=user,
            ).exists():
                return True

        return False

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        from apps.core.droits import est_administrateur, est_dg

        if user.is_superuser or est_dg(user) or est_administrateur(user):
            return True

        # GardePermissionProjet pour "projets.affecter_membres" (ex: CP affecté)
        garde = GardePermissionProjet.pour("projets.affecter_membres")()
        if garde.has_object_permission(request, view, obj):
            return True

        # Ou affectation active CT de l'utilisateur sur ce projet
        from apps.projets.models import AffectationProjet, Projet

        projet = obj if isinstance(obj, Projet) else getattr(obj, "projet", None)
        return bool(
            projet
            and (
                AffectationProjet.objects.filter(
                    projet=projet,
                    utilisateur=user,
                    role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
                    est_actif=True,
                    supprime_le__isnull=True,
                ).exists()
                or getattr(projet, "conducteur_travaux_id", None) == user.id
            )
        )
