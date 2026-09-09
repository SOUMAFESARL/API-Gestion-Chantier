"""Permissions transverses — contrôle d'accès à deux niveaux.

Socle Commun §2.3 : les deux niveaux sont **cumulatifs**.

  Niveau 1 — rôle global        : ce que la personne a le droit de faire
  Niveau 2 — appartenance projet: sur quels chantiers elle a le droit de le faire

Le rôle seul ne donne accès à rien (RG-01). Le contrôle est fait côté
serveur à chaque requête : un utilisateur qui modifie l'URL à la main
reçoit un 403, sans aucune donnée.
"""

from rest_framework import permissions

from apps.core.enums import RoleGlobal


class RoleRequis(permissions.BasePermission):
    """Niveau 1 — restreint une vue à une liste de rôles globaux.

    Usage :

        class VueBudget(APIView):
            permission_classes = [RoleRequis.pour("DG", "DF")]
    """

    roles_autorises: tuple[str, ...] = ()
    message = "Votre rôle ne permet pas d'accéder à cette ressource."

    @classmethod
    def pour(cls, *roles: str):
        inconnus = set(roles) - set(RoleGlobal.values)
        if inconnus:
            raise ValueError(f"Rôles inconnus : {sorted(inconnus)}")
        return type("RoleRequisSpecifique", (cls,), {"roles_autorises": tuple(roles)})

    def has_permission(self, request, view) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False
        if not self.roles_autorises:
            return True
        return utilisateur.role_global in self.roles_autorises


class MembreDuProjet(permissions.BasePermission):
    """Niveau 2 — l'utilisateur doit être affecté au projet visé.

    L'objet doit exposer un `projet_id`, un `projet`, ou être un projet.
    """

    message = "Vous n'êtes pas affecté à ce projet."

    def has_object_permission(self, request, view, obj) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False

        projet_id = self._extraire_projet_id(obj)
        if projet_id is None:
            return False

        # Résolution tardive : `core` est la couche la plus basse et ne doit
        # pas importer un module métier (règle R1 de la structure de projet).
        from django.apps import apps as registre

        try:
            AffectationProjet = registre.get_model("projets", "AffectationProjet")
        except LookupError:  # pragma: no cover — tant que le module 1 n'existe pas
            return False

        return AffectationProjet.objects.filter(
            utilisateur=utilisateur, projet_id=projet_id, est_actif=True
        ).exists()

    @staticmethod
    def _extraire_projet_id(obj):
        if hasattr(obj, "projet_id"):
            return obj.projet_id
        if obj.__class__.__name__ == "Projet":
            return obj.pk
        if hasattr(obj, "lot") and hasattr(obj.lot, "projet_id"):
            return obj.lot.projet_id
        return None


class LectureSeule(permissions.BasePermission):
    """N'autorise que GET, HEAD et OPTIONS."""

    def has_permission(self, request, view) -> bool:
        return request.method in permissions.SAFE_METHODS


class PermissionModule(permissions.BasePermission):
    """Contrôle d'accès dynamique basé sur la matrice des modules et le niveau requis.

    Usage :
        class VueRapport(APIView):
            permission_classes = [PermissionModule.pour("chantier", NiveauAcces.ECRITURE)]
    """

    module: str = ""
    niveau_requis: int = 1
    message = "Vos habilitations ne permettent pas d'effectuer cette action sur ce module."

    @classmethod
    def pour(cls, module: str, niveau_requis: int = 1):
        return type(
            "PermissionModuleSpecifique",
            (cls,),
            {"module": module, "niveau_requis": int(niveau_requis)},
        )

    def has_permission(self, request, view) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False
        if (
            utilisateur.is_superuser
            or getattr(utilisateur, "is_owner", False)
            or getattr(utilisateur, "is_dg", False)
            or utilisateur.role_global in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
        ):
            return True

        from django.apps import apps as registre

        try:
            Role = registre.get_model("accounts", "Role")
            RoleModulePermission = registre.get_model("accounts", "RoleModulePermission")
        except LookupError:
            return True

        role = utilisateur.role_personnalise
        if not role:
            role = Role.objects.filter(
                code=utilisateur.role_global, supprime_le__isnull=True
            ).first()

        if not role:
            return False

        perm = RoleModulePermission.objects.filter(
            role=role, module=self.module, supprime_le__isnull=True
        ).first()
        if not perm:
            return False

        return perm.niveau >= self.niveau_requis

    def has_object_permission(self, request, view, obj) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False
        if (
            utilisateur.is_superuser
            or getattr(utilisateur, "is_owner", False)
            or getattr(utilisateur, "is_dg", False)
            or utilisateur.role_global in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
        ):
            return True

        projet_id = MembreDuProjet._extraire_projet_id(obj)
        if not projet_id:
            return self.has_permission(request, view)

        from django.apps import apps as registre

        try:
            AffectationProjet = registre.get_model("projets", "AffectationProjet")
            ProjetRoleModuleOverride = registre.get_model("projets", "ProjetRoleModuleOverride")
            Role = registre.get_model("accounts", "Role")
            RoleModulePermission = registre.get_model("accounts", "RoleModulePermission")
        except LookupError:
            return True

        est_direction = utilisateur.role_global in (
            RoleGlobal.DIRECTEUR_GENERAL,
            RoleGlobal.DIRECTEUR_FINANCIER,
        )
        affectation = AffectationProjet.objects.filter(
            utilisateur=utilisateur, projet_id=projet_id, est_actif=True
        ).first()

        if not affectation and not est_direction:
            return False

        role = None
        if affectation:
            role = affectation.role
            if not role:
                role = Role.objects.filter(
                    code=affectation.role_projet, supprime_le__isnull=True
                ).first()
        if not role:
            role = (
                utilisateur.role_personnalise
                or Role.objects.filter(
                    code=utilisateur.role_global, supprime_le__isnull=True
                ).first()
            )

        if not role:
            return False

        override = ProjetRoleModuleOverride.objects.filter(
            projet_id=projet_id, role=role, module=self.module, supprime_le__isnull=True
        ).first()
        if override:
            return override.niveau >= self.niveau_requis

        perm = RoleModulePermission.objects.filter(
            role=role, module=self.module, supprime_le__isnull=True
        ).first()
        if not perm:
            return False

        return perm.niveau >= self.niveau_requis
