"""Moteur unique de décision d'habilitation et contrôle d'accès RBAC souverain.

Règle absolue :
1. SuperAdmin -> tous les points de contrôle du REGISTRE.
2. DG de l'entreprise -> tous les codes des modules actifs de l'entreprise + administration.
3. Autre rôle -> intersection entre :
   a) modules actifs de l'entreprise (EntrepriseModule.est_actif=True)
   b) niveau accordé au rôle sur le module (RoleModulePermission.niveau)
   c) plafond du modèle associé au rôle si applicable (ModeleRoleModule.niveau_max)
"""

from django.db import connection, models
from rest_framework import permissions

from apps.core.enums import RoleGlobal
from apps.core.registre_permissions import REGISTRE, permissions_du_module

__all__ = ["APermission", "a_permission", "permissions_effectives"]

MODULES_SYSTEME = frozenset({"administration"})


def _obtenir_modules_actifs(tenant=None) -> set[str]:
    """Retourne l'ensemble des codes de modules actifs pour l'entreprise courante."""
    if tenant is None:
        tenant = getattr(connection, "tenant", None)

    # 1. Vérifier les souscriptions EntrepriseModule dans le schéma public
    if tenant and getattr(tenant, "schema_name", "public") != "public":
        try:
            from apps.catalogue.models import EntrepriseModule

            em_qs = EntrepriseModule.objects.filter(entreprise=tenant, supprime_le__isnull=True)
            if em_qs.exists():
                actifs = set(
                    em_qs.filter(est_actif=True).values_list("module__code", flat=True)
                )
                actifs.update(MODULES_SYSTEME)
                return {m.lower() for m in actifs}
        except Exception:
            pass

        # 2. Repli sur la table Module locale du tenant
        try:
            from apps.accounts.models import Module

            m_qs = Module.objects.filter(supprime_le__isnull=True)
            if m_qs.exists():
                actifs = set(m_qs.filter(est_actif=True).values_list("code", flat=True))
                actifs.update(MODULES_SYSTEME)
                return {m.lower() for m in actifs}
        except Exception:
            pass

    # 3. Repli si schéma public ou environnement de test
    try:
        from apps.catalogue.models import CatalogueModule

        c_mods = set(
            CatalogueModule.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).values_list("code", flat=True)
        )
        if c_mods:
            c_mods.update(MODULES_SYSTEME)
            return {m.lower() for m in c_mods}
    except Exception:
        pass

    return {p.module for p in REGISTRE.values()}


def _obtenir_plafonds_modele(code_role: str) -> dict[str, int]:
    """Retourne les plafonds {module_code: niveau_max} définis par le ModeleRole s'il existe."""
    plafonds: dict[str, int] = {}
    if not code_role:
        return plafonds
    try:
        from apps.catalogue.models import ModeleRoleModule

        mrms = ModeleRoleModule.objects.filter(
            modele_role__code=code_role,
            modele_role__est_actif=True,
            modele_role__supprime_le__isnull=True,
        ).select_related("module")
        for mrm in mrms:
            mod_code = mrm.module.code if mrm.module else getattr(mrm, "module_code", "")
            if mod_code:
                plafonds[mod_code.lower()] = mrm.niveau_max
    except Exception:
        pass
    return plafonds


def permissions_effectives(collaborateur, request=None, tenant=None) -> set[str]:
    """Calcule l'ensemble exact des codes de permissions accordées au collaborateur."""
    if not collaborateur or not getattr(collaborateur, "is_authenticated", False):
        return set()

    if request and hasattr(request, "_permissions_effectives_cache"):
        return request._permissions_effectives_cache

    # 1. SuperAdmin plateforme : accès inconditionnel à tout le registre
    if getattr(collaborateur, "is_superuser", False):
        perms = set(REGISTRE.keys())
        if request:
            request._permissions_effectives_cache = perms
        return perms

    modules_actifs = _obtenir_modules_actifs(tenant)

    # 2. DG ou Propriétaire : toutes les permissions des modules actifs de l'entreprise
    is_dg = bool(
        getattr(collaborateur, "is_owner", False)
        or getattr(collaborateur, "is_dg", False)
        or getattr(collaborateur, "role_global", None) in (RoleGlobal.DIRECTEUR_GENERAL, "DG")
        or (
            getattr(collaborateur, "role_personnalise", None)
            and getattr(collaborateur.role_personnalise, "code", "") == "DG"
        )
    )
    if is_dg:
        perms = {code for code, def_p in REGISTRE.items() if def_p.module in modules_actifs}
        if request:
            request._permissions_effectives_cache = perms
        return perms

    # 3. Autre rôle
    role = getattr(collaborateur, "role_personnalise", None)
    if not role and hasattr(collaborateur, "role_global"):
        try:
            from apps.accounts.models import Role

            role = Role.objects.filter(
                code=collaborateur.role_global, supprime_le__isnull=True
            ).first()
        except Exception:
            role = None

    if not role or not getattr(role, "est_actif", True):
        if request:
            request._permissions_effectives_cache = set()
        return set()

    # Récupérer les niveaux accordés au rôle par module
    niveaux_role: dict[str, int] = {}
    try:
        from apps.accounts.models import RoleModulePermission

        rmps = RoleModulePermission.objects.filter(
            role=role,
            supprime_le__isnull=True,
        )
        if hasattr(rmps, "select_related"):
            rmps = rmps.select_related("module", "module_catalogue")

        for rmp in rmps:
            mod_code = None
            if getattr(rmp, "module_catalogue_id", None) and getattr(rmp, "module_catalogue", None):
                mod_code = rmp.module_catalogue.code
            elif getattr(rmp, "module_id", None) and getattr(rmp, "module", None):
                mod_code = rmp.module.code
            if mod_code:
                niveaux_role[mod_code.lower()] = (
                    rmp.niveau if getattr(rmp, "niveau", None) is not None else 0
                )
    except Exception:
        pass

    plafonds = _obtenir_plafonds_modele(getattr(role, "code", ""))

    perms_accordees: set[str] = set()
    for mod_code in modules_actifs:
        mod_key = mod_code.lower()
        # Niveau accordé en base (ou repli sur le plafond template si module non configuré)
        niveau = niveaux_role.get(mod_key, plafonds.get(mod_key, 0))
        # Plafond template (le DG ne peut pas accorder plus que le template)
        if mod_key in plafonds:
            niveau = min(niveau, plafonds[mod_key])

        if niveau > 0:
            perms_accordees.update(permissions_du_module(mod_key, niveau))

    if request:
        request._permissions_effectives_cache = perms_accordees
    return perms_accordees


def a_permission(collaborateur, code_permission: str, request=None, tenant=None) -> bool:
    """Vérifie si le collaborateur possède un code de permission spécifique."""
    perms = permissions_effectives(collaborateur, request=request, tenant=tenant)
    return code_permission in perms


class APermission(permissions.BasePermission):
    """Classe DRF pour sécuriser les vues par point de contrôle unifié.

    Usage :
        permission_classes = [IsAuthenticated, APermission]
        permission_requise = "projets.ecrire"
    OU
        permission_classes = [IsAuthenticated, APermission.pour("projets.ecrire")]
    OU
        permissions_par_action = {"create": "projets.creer", "list": "projets.lire"}
    """

    permission_requise: str | None = None
    message = "Vos habilitations ne vous permettent pas d'effectuer cette action."

    @classmethod
    def pour(cls, code_permission: str):
        return type("APermissionSpecifique", (cls,), {"permission_requise": code_permission})

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        perm_code = self.permission_requise
        if hasattr(view, "get_permission_requise") and callable(view.get_permission_requise):
            perm_code = view.get_permission_requise()
        elif hasattr(view, "permissions_par_action") and hasattr(view, "action"):
            perm_code = view.permissions_par_action.get(view.action, self.permission_requise)
        elif getattr(view, "permission_requise", None):
            perm_code = view.permission_requise

        if callable(perm_code):
            perm_code = perm_code(request, view)

        if not perm_code:
            return True

        return a_permission(user, perm_code, request=request)
