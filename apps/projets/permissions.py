"""Permissions DRF propres au module."""

from rest_framework.permissions import BasePermission

from apps.core.permissions import GardePermissionProjet


class PeutRetirerDuProjet(BasePermission):
    """Retirer quelqu'un d'un chantier : qui affecte les membres (`projets.affecter_membres`),
    ou qui détient `projets.retirer_membres` par son rôle sur ce projet.

    Remplace la règle codée sur le nom du rôle « CT » (décisions v1.2, §13bis : plus aucune
    règle ne dépend du nom d'un rôle). Par défaut, le chef de projet et le conducteur de travaux
    ont `projets.retirer_membres`.
    """

    message = "Vous n'avez pas les droits nécessaires pour cette action."

    def _peut_retirer(self, request, projet) -> bool:
        from apps.projets.services.perimetres import perimetre_de

        return perimetre_de(request.user, projet, request).peut_quelque_part(
            "projets.retirer_membres"
        )

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        from apps.core.droits import a_permission, est_administrateur, est_dg

        if user.is_superuser or est_dg(user) or est_administrateur(user):
            return True
        if a_permission(user, "projets.affecter_membres", request=request):
            return True
        projet_id = view.kwargs.get("projet_id") or view.kwargs.get("pk")
        if projet_id:
            from apps.projets.models import Projet

            projet = Projet.objects.filter(pk=projet_id).first()
            return bool(projet and self._peut_retirer(request, projet))
        return False

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        from apps.core.droits import est_administrateur, est_dg

        if user.is_superuser or est_dg(user) or est_administrateur(user):
            return True

        garde = GardePermissionProjet.pour("projets.affecter_membres")()
        if garde.has_object_permission(request, view, obj):
            return True

        from apps.projets.models import Projet

        projet = obj if isinstance(obj, Projet) else getattr(obj, "projet", None)
        return bool(projet and self._peut_retirer(request, projet))
