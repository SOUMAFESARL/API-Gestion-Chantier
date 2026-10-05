"""Permissions transverses — contrôle d'accès à deux niveaux.

Socle Commun §2.3 : les deux niveaux sont **cumulatifs**.

  Niveau 1 — rôle global        : ce que la personne a le droit de faire
  Niveau 2 — appartenance projet: sur quels chantiers elle a le droit de le faire

Le rôle seul ne donne accès à rien (RG-01). Le contrôle est fait côté
serveur à chaque requête : un utilisateur qui modifie l'URL à la main
reçoit un 403, sans aucune donnée.
"""

from django.db import models
from rest_framework import permissions

from apps.core.enums import RoleGlobal


__all__ = [
    "EstDirection",
    "LectureSeule",
    "MembreDuProjet",
    "PermissionModule",
    "RoleRequis",
    "ScopedProjetQuerySetMixin",
    "filtrer_queryset_par_affectations",
    "obtenir_projets_ids_actifs_utilisateur",
]


def obtenir_projets_ids_actifs_utilisateur(user, request=None) -> list:
    """Récupère et met en cache sur request la liste des IDs de projets affectés ou gérés."""
    if not user or not user.is_authenticated:
        return []
    if request and hasattr(request, "_rbac_projets_ids_actifs"):
        return request._rbac_projets_ids_actifs

    from django.apps import apps as registre
    from django.db.models import Q

    try:
        AffectationProjet = registre.get_model("projets", "AffectationProjet")
        Projet = registre.get_model("projets", "Projet")
    except LookupError:
        return []

    # 1. Projets issus d'affectations actives
    projets_ids = set(
        AffectationProjet.objects.filter(
            utilisateur=user, est_actif=True, supprime_le__isnull=True
        ).values_list("projet_id", flat=True)
    )

    # 2. Projets où l'utilisateur est désigné comme chef de projet ou conducteur de travaux direct
    projets_geres = set(
        Projet.objects.filter(
            Q(chef_projet=user) | Q(conducteur_travaux=user),
            supprime_le__isnull=True,
        ).values_list("id", flat=True)
    )

    projets_ids = list(projets_ids.union(projets_geres))
    if request:
        request._rbac_projets_ids_actifs = projets_ids
    return projets_ids


def filtrer_queryset_par_affectations(qs, user, champ_projet="id", request=None):
    """Restreint un QuerySet aux seuls chantiers où l'utilisateur est affecté.

    Pour ceux qui ont 'projets.voir_tous' (DG, Superuser, Administrateur) : vision consolidée sans restriction.
    Pour les collaborateurs opérationnels : vision bornée aux chantiers affectés.
    """
    if not user or not user.is_authenticated:
        return qs.none()

    from apps.core.droits import a_permission

    if a_permission(user, "projets.voir_tous", request=request):
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


class EstDirection(permissions.BasePermission):
    """Autorise uniquement la Direction : DG, Administrateur, Propriétaire ou Superuser."""

    message = "Seule la Direction (DG / Administrateur) est autorisée à effectuer cette action."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        from apps.core.droits import a_permission

        return bool(
            user.is_superuser
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or a_permission(user, "administration.collaborateurs_gerer", request=request)
            or a_permission(user, "administration.roles_gerer", request=request)
        )


class MembreDuProjet(permissions.BasePermission):
    """Niveau 2 — l'utilisateur doit être affecté au projet visé avec mémoïsation O(1).

    L'objet doit exposer un `projet_id`, un `projet`, ou être un projet.
    """

    message = "Vous n'êtes pas affecté à ce projet."

    def has_object_permission(self, request, view, obj) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False

        from apps.core.droits import a_permission

        if a_permission(utilisateur, "projets.voir_tous", request=request):
            return True

        projet_id = self._extraire_projet_id(obj)
        if projet_id is None:
            return False

        if not hasattr(request, "_rbac_membre_projet_cache"):
            request._rbac_membre_projet_cache = {}

        cle = (str(utilisateur.id), str(projet_id))
        if cle in request._rbac_membre_projet_cache:
            return request._rbac_membre_projet_cache[cle]

        projets_ids = obtenir_projets_ids_actifs_utilisateur(utilisateur, request=request)
        est_membre = (projet_id in projets_ids) or (str(projet_id) in [str(pid) for pid in projets_ids])
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
    """Contrôle d'accès dynamique granulaire avec mémoïsation O(1) par requête HTTP."""

    module: str = ""
    permission_requise: str = "LECTURE"
    niveau_requis: int = 1
    message = "Vos habilitations ne permettent pas d'effectuer cette action sur ce module."

    @classmethod
    def pour(cls, module: str, permission_ou_niveau=1):
        if isinstance(permission_ou_niveau, int):
            mapping = {1: "LECTURE", 2: "ECRITURE", 3: "VALIDATION"}
            perm_code = mapping.get(permission_ou_niveau, "LECTURE")
            return type(
                "PermissionModuleSpecifique",
                (cls,),
                {
                    "module": str(module).lower(),
                    "permission_requise": perm_code,
                    "niveau_requis": int(permission_ou_niveau),
                },
            )
        else:
            return type(
                "PermissionModuleSpecifique",
                (cls,),
                {
                    "module": str(module).lower(),
                    "permission_requise": str(permission_ou_niveau).upper(),
                    "niveau_requis": 1,
                },
            )

    def has_permission(self, request, view) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False

        if (
            utilisateur.is_superuser
            or getattr(utilisateur, "is_owner", False)
            or getattr(utilisateur, "is_dg", False)
            or getattr(utilisateur, "role_global", None) in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
        ):
            return True

        from django.apps import apps as registre

        try:
            Role = registre.get_model("accounts", "Role")
            RoleModulePermission = registre.get_model("accounts", "RoleModulePermission")
        except LookupError:
            Role = None
            RoleModulePermission = None

        if Role and RoleModulePermission:
            role = utilisateur.role_personnalise or Role.objects.filter(
                code=utilisateur.role_global, supprime_le__isnull=True
            ).first()
            if role:
                from django.db import models as dj_models

                rmp = RoleModulePermission.objects.filter(
                    dj_models.Q(module_catalogue__code=self.module) | dj_models.Q(module__code=self.module),
                    role=role,
                    supprime_le__isnull=True,
                ).first()
                if rmp:
                    if rmp.niveau == 0 and not rmp.permissions_catalogue.filter(est_actif=True, supprime_le__isnull=True).exists():
                        return False
                    if rmp.permissions_catalogue.filter(
                        code__iexact=self.permission_requise, est_actif=True, supprime_le__isnull=True
                    ).exists():
                        return True
                    if self.permission_requise in ("LECTURE", "ECRITURE", "VALIDATION"):
                        if rmp.niveau is not None and rmp.niveau >= self.niveau_requis:
                            return True

        from apps.core.droits import permissions_effectives
        from apps.core.registre_permissions import REGISTRE

        perms = permissions_effectives(utilisateur, request=request)
        for def_p in REGISTRE.values():
            if def_p.module == self.module and def_p.rang >= self.niveau_requis and def_p.code in perms:
                return True
        return False

    def has_object_permission(self, request, view, obj) -> bool:
        utilisateur = request.user
        if not utilisateur or not utilisateur.is_authenticated:
            return False

        from apps.core.droits import a_permission

        if a_permission(utilisateur, "projets.voir_tous", request=request):
            return True

        projet_id = MembreDuProjet._extraire_projet_id(obj)
        if not projet_id:
            return self.has_permission(request, view)

        cle_cache = (str(utilisateur.id), self.module, self.permission_requise, str(projet_id))
        if not hasattr(request, "_rbac_object_permissions_cache"):
            request._rbac_object_permissions_cache = {}

        if cle_cache in request._rbac_object_permissions_cache:
            return request._rbac_object_permissions_cache[cle_cache]

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
            request._rbac_object_permissions_cache[cle_cache] = False
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
            request._rbac_object_permissions_cache[cle_cache] = False
            return False

        override = ProjetRoleModuleOverride.objects.filter(
            models.Q(module_catalogue__code=self.module) | models.Q(module__code=self.module),
            projet_id=projet_id,
            role=role,
            supprime_le__isnull=True,
        ).first()
        if override:
            if override.niveau == 0:
                request._rbac_object_permissions_cache[cle_cache] = False
                return False
            has_perm = (
                override.permissions_catalogue.filter(
                    code=self.permission_requise, est_actif=True, supprime_le__isnull=True
                ).exists()
                or override.permissions.filter(
                    code=self.permission_requise, est_actif=True, supprime_le__isnull=True
                ).exists()
            )
            has_override_m2m = override.permissions_catalogue.exists() or override.permissions.exists()
            if not has_perm and not has_override_m2m and override.niveau is not None and override.niveau > 0:
                if self.permission_requise == "LECTURE" and override.niveau >= 1:
                    has_perm = True
                elif self.permission_requise == "ECRITURE" and override.niveau >= 2:
                    has_perm = True
                elif self.permission_requise == "VALIDATION" and override.niveau >= 3:
                    has_perm = True
            request._rbac_object_permissions_cache[cle_cache] = has_perm
            return has_perm

        perm = RoleModulePermission.objects.filter(
            models.Q(module_catalogue__code=self.module) | models.Q(module__code=self.module),
            role=role,
            supprime_le__isnull=True,
        ).first()
        if not perm or perm.niveau == 0:
            request._rbac_object_permissions_cache[cle_cache] = False
            return False

        has_perm = perm.permissions_catalogue.filter(
            code=self.permission_requise, est_actif=True, supprime_le__isnull=True
        ).exists()
        has_perm_m2m = perm.permissions_catalogue.exists()
        if not has_perm and not has_perm_m2m and perm.niveau is not None and perm.niveau > 0:
            if self.permission_requise == "LECTURE" and perm.niveau >= 1:
                has_perm = True
            elif self.permission_requise == "ECRITURE" and perm.niveau >= 2:
                has_perm = True
            elif self.permission_requise == "VALIDATION" and perm.niveau >= 3:
                has_perm = True

        request._rbac_object_permissions_cache[cle_cache] = has_perm
        return has_perm

