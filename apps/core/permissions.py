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


__all__ = [
    "LectureSeule",
    "MembreDuProjet",
    "PermissionModule",
    "RoleRequis",
    "ScopedProjetQuerySetMixin",
    "filtrer_queryset_par_affectations",
    "obtenir_projets_ids_actifs_utilisateur",
]


def obtenir_projets_ids_actifs_utilisateur(user, request=None) -> list:
    """Récupère et met en cache sur request la liste des IDs de projets affectés."""
    if not user or not user.is_authenticated:
        return []
    if request and hasattr(request, "_rbac_projets_ids_actifs"):
        return request._rbac_projets_ids_actifs

    from django.apps import apps as registre

    try:
        AffectationProjet = registre.get_model("projets", "AffectationProjet")
    except LookupError:
        return []

    projets_ids = list(
        AffectationProjet.objects.filter(
            utilisateur=user, est_actif=True, supprime_le__isnull=True
        ).values_list("projet_id", flat=True)
    )
    if request:
        request._rbac_projets_ids_actifs = projets_ids
    return projets_ids


def filtrer_queryset_par_affectations(qs, user, champ_projet="id", request=None):
    """Restreint un QuerySet aux seuls chantiers où l'utilisateur est affecté.

    Pour la Direction (DG, Admin, Propriétaire, Superuser) : vision consolidée sans restriction.
    Pour les collaborateurs opérationnels : vision bornée aux chantiers affectés.
    """
    if not user or not user.is_authenticated:
        return qs.none()

    est_direction = (
        user.is_superuser
        or getattr(user, "is_owner", False)
        or getattr(user, "is_dg", False)
        or getattr(user, "role_global", None) in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
    )
    if est_direction:
        return qs

    projets_ids = obtenir_projets_ids_actifs_utilisateur(user, request=request)
    filtre = {f"{champ_projet}__in": projets_ids}
    return qs.filter(**filtre)


class ScopedProjetQuerySetMixin:
    """Mixin DRF appliquant le scoping automatique par affectation sur get_queryset()."""

    champ_projet_scoping: str = "id"

    def filtrer_par_affectation(self, qs, champ_projet=None):
        champ = champ_projet or getattr(self, "champ_projet_scoping", "id")
        return filtrer_queryset_par_affectations(
            qs, self.request.user, champ_projet=champ, request=self.request
        )


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
    """Niveau 2 — l'utilisateur doit être affecté au projet visé avec mémoïsation O(1).

    L'objet doit exposer un `projet_id`, un `projet`, ou être un projet.
    """

    message = "Vous n'êtes pas affecté à ce projet."

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

        projet_id = self._extraire_projet_id(obj)
        if projet_id is None:
            return False

        if not hasattr(request, "_rbac_membre_projet_cache"):
            request._rbac_membre_projet_cache = {}

        cle = (str(utilisateur.id), str(projet_id))
        if cle in request._rbac_membre_projet_cache:
            return request._rbac_membre_projet_cache[cle]

        from django.apps import apps as registre

        try:
            AffectationProjet = registre.get_model("projets", "AffectationProjet")
        except LookupError:
            return False

        est_membre = AffectationProjet.objects.filter(
            utilisateur=utilisateur,
            projet_id=projet_id,
            est_actif=True,
            supprime_le__isnull=True,
        ).exists()
        request._rbac_membre_projet_cache[cle] = est_membre
        return est_membre

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
    """Contrôle d'accès dynamique avec mémoïsation O(1) par requête HTTP."""

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

        if not hasattr(request, "_rbac_module_permissions_cache"):
            request._rbac_module_permissions_cache = {}

        if self.module in request._rbac_module_permissions_cache:
            niveau = request._rbac_module_permissions_cache[self.module]
            return niveau >= self.niveau_requis

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
            request._rbac_module_permissions_cache[self.module] = 0
            return False

        perm = RoleModulePermission.objects.filter(
            role=role, module__code=self.module, supprime_le__isnull=True
        ).first()
        niveau = perm.niveau if perm else 0
        request._rbac_module_permissions_cache[self.module] = niveau
        return niveau >= self.niveau_requis

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

        cle_cache = (str(utilisateur.id), self.module, str(projet_id))
        if not hasattr(request, "_rbac_object_permissions_cache"):
            request._rbac_object_permissions_cache = {}

        if cle_cache in request._rbac_object_permissions_cache:
            niveau = request._rbac_object_permissions_cache[cle_cache]
            return niveau >= self.niveau_requis

        from django.apps import apps as registre

        try:
            AffectationProjet = registre.get_model("projets", "AffectationProjet")
            ProjetRoleModuleOverride = registre.get_model("projets", "ProjetRoleModuleOverride")
            Role = registre.get_model("accounts", "Role")
            RoleModulePermission = registre.get_model("accounts", "RoleModulePermission")
        except LookupError:
            return True

        affectation = AffectationProjet.objects.filter(
            utilisateur=utilisateur,
            projet_id=projet_id,
            est_actif=True,
            supprime_le__isnull=True,
        ).first()

        if not affectation:
            request._rbac_object_permissions_cache[cle_cache] = 0
            return False

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
            request._rbac_object_permissions_cache[cle_cache] = 0
            return False

        override = ProjetRoleModuleOverride.objects.filter(
            projet_id=projet_id, role=role, module__code=self.module, supprime_le__isnull=True
        ).first()
        if override:
            niveau = override.niveau
            request._rbac_object_permissions_cache[cle_cache] = niveau
            return niveau >= self.niveau_requis

        perm = RoleModulePermission.objects.filter(
            role=role, module__code=self.module, supprime_le__isnull=True
        ).first()
        niveau = perm.niveau if perm else 0
        request._rbac_object_permissions_cache[cle_cache] = niveau
        return niveau >= self.niveau_requis

