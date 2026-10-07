"""Moteur unique de décision d'habilitation et contrôle d'accès RBAC souverain.

Règles :
1. SuperAdmin -> tous les points de contrôle du REGISTRE.
2. DG de l'entreprise -> toutes les permissions actives des modules actifs de l'entreprise + administration.
3. Autre rôle -> liste explicite des permissions cochées dans permissions_catalogue,
   restreinte aux modules actifs de l'entreprise et aux permissions actives du catalogue (A-04, A-06, A-12).
"""

from django.db import connection, models
from rest_framework import permissions

from apps.core.enums import RoleGlobal
from apps.core.registre_permissions import REGISTRE

__all__ = [
    "APermission",
    "a_permission",
    "permissions_effectives",
    "permissions_du_role",
    "est_dg",
    "peut_voir_montants",
    "DROITS_ADMIN_AD",
    "DROITS_ADMIN_RESERVES_DG",
]

# Les 6 droits d'administration fixes de l'AD (B-04)
DROITS_ADMIN_AD = frozenset({
    "administration.collaborateurs_voir",
    "administration.collaborateurs_gerer",
    "administration.roles_gerer",
    "administration.abonnement_voir",
    "administration.factures_voir",
    "administration.onboarding_suivre",
})

# Droits d'administration strictement reserves au DG (B-04)
DROITS_ADMIN_RESERVES_DG = frozenset({
    "administration.entreprise_modifier",
    "administration.abonnement_gerer",
})

MODULES_SYSTEME = frozenset({"administration"})


def est_dg(utilisateur) -> bool:
    """Règle B-03 : Détermine de manière unique et souveraine si l'utilisateur est le DG."""
    if not utilisateur or not getattr(utilisateur, "is_authenticated", False):
        return False
    if getattr(utilisateur, "is_owner", False):
        return True
    if getattr(utilisateur, "role_id", None) and getattr(utilisateur, "role", None):
        if getattr(utilisateur.role, "code", "") == "DG":
            return True
    if getattr(utilisateur, "role_personnalise_id", None) and getattr(utilisateur, "role_personnalise", None):
        if getattr(utilisateur.role_personnalise, "code", "") == "DG":
            return True
    if getattr(utilisateur, "role_global", None) in (RoleGlobal.DIRECTEUR_GENERAL, "DG", "DIRECTEUR_GENERAL"):
        return True
    return False


def peut_voir_montants(utilisateur, request=None) -> bool:
    """Règle E-11 : Détermine si l'utilisateur possède le droit de voir les montants financiers.

    Détenteurs réels (annexe 1) : DG, DF, DO, CP.
    Non-détenteurs : AD, CT, CC, MAG, BAI, VI.
    """
    if not utilisateur or not getattr(utilisateur, "is_authenticated", False):
        return False
    if est_dg(utilisateur):
        return True
    return a_permission(utilisateur, "projets.voir_montants", request=request)


def _obtenir_modules_actifs(tenant=None) -> set[str]:
    """Retourne l'ensemble des codes de modules actifs pour l'entreprise courante."""
    from apps.tenants.models import Entreprise

    if tenant is None or not isinstance(tenant, Entreprise):
        schema = getattr(connection, "schema_name", "public")
        if schema and schema != "public":
            try:
                tenant = Entreprise.objects.filter(schema_name=schema).first()
            except Exception:
                tenant = None

    # 1. Vérifier les souscriptions EntrepriseModule dans le schéma public
    if tenant and getattr(tenant, "schema_name", "public") != "public":
        try:
            from apps.catalogue.models import EntrepriseModule, CatalogueModule

            em_qs = EntrepriseModule.objects.filter(entreprise=tenant, supprime_le__isnull=True)
            if em_qs.exists():
                inactifs = {
                    m.lower()
                    for m in em_qs.filter(est_actif=False).values_list("module__code", flat=True)
                }
                actifs_souscrits = {
                    m.lower()
                    for m in em_qs.filter(est_actif=True).values_list("module__code", flat=True)
                }
                tous_actifs = {
                    m.lower()
                    for m in CatalogueModule.objects.filter(
                        est_actif=True, supprime_le__isnull=True
                    ).values_list("code", flat=True)
                }
                resultats = (tous_actifs | actifs_souscrits) - inactifs
                resultats.update(MODULES_SYSTEME)
                return resultats
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


def permissions_effectives(collaborateur, request=None, tenant=None) -> set[str]:
    """Calcule l'ensemble exact des codes de permissions accordées au collaborateur (A-04, A-06, A-12)."""
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

    from apps.catalogue.models import CataloguePermission

    # 2. DG ou Propriétaire : toutes les permissions actives des modules actifs + administration
    if est_dg(collaborateur):
        perms: set[str] = set()
        # Catalogue en base
        try:
            cat_perms_qs = CataloguePermission.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).prefetch_related("modules")
            for cp in cat_perms_qs:
                c_code = cp.code.lower()
                c_mod = c_code.split(".")[0] if "." in c_code else ""
                mods_cp = {m.code.lower() for m in cp.modules.all()}
                if c_mod and c_mod not in modules_actifs and c_mod != "administration":
                    continue
                if (
                    c_mod in modules_actifs
                    or c_mod == "administration"
                    or any(m in modules_actifs for m in mods_cp)
                ):
                    perms.add(c_code)
        except Exception:
            pass

        # Compléter avec REGISTRE pour les modules actifs
        for code, def_p in REGISTRE.items():
            if def_p.module in modules_actifs or def_p.module == "administration":
                perms.add(code.lower())

        if request:
            request._permissions_effectives_cache = perms
        return perms

    # 3. Autre rôle
    role = getattr(collaborateur, "role_personnalise", None)
    code_role = getattr(collaborateur, "role_global", "") or ""
    if not role and getattr(collaborateur, "role_id", None):
        role = getattr(collaborateur, "role", None)

    if not role and code_role:
        try:
            from apps.accounts.models import Role

            role = Role.objects.filter(
                code=code_role, supprime_le__isnull=True
            ).first()
            if not role:
                from apps.accounts.services.roles import initialiser_roles_par_defaut
                initialiser_roles_par_defaut()
                role = Role.objects.filter(
                    code=code_role, supprime_le__isnull=True
                ).first()
        except Exception:
            role = None

    if not role or not getattr(role, "est_actif", True):
        if request:
            request._permissions_effectives_cache = set()
        return set()

    # Règle A-04 : lit uniquement la liste cochée dans permissions_catalogue
    # Règle A-06 : filtre les modules désactivés pour l'entreprise et les permissions inactives
    # Règle A-12 : aucun ancien plafond de modèle n'intervient
    perms_accordees: set[str] = set()
    try:
        from apps.accounts.models import RoleModulePermission

        rmps = RoleModulePermission.objects.filter(
            role=role,
            supprime_le__isnull=True,
        ).select_related("module", "module_catalogue")

        if not rmps.exists() and (getattr(role, "est_systeme", False) or getattr(role, "code", "") in {"DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"}):
            from apps.accounts.services.roles import initialiser_roles_par_defaut
            initialiser_roles_par_defaut()
            rmps = RoleModulePermission.objects.filter(
                role=role,
                supprime_le__isnull=True,
            ).select_related("module", "module_catalogue")

        for rmp in rmps:
            mod_code = None
            if getattr(rmp, "module_catalogue_id", None) and getattr(rmp, "module_catalogue", None):
                mod_code = rmp.module_catalogue.code
            elif getattr(rmp, "module_id", None) and getattr(rmp, "module", None):
                mod_code = rmp.module.code

            if not mod_code:
                continue

            mod_key = mod_code.lower()
            if mod_key not in modules_actifs and mod_key != "administration":
                continue

            codes_cochés = set(
                rmp.permissions_catalogue.filter(
                    est_actif=True,
                    supprime_le__isnull=True,
                ).values_list("code", flat=True)
            )

            # Permissions actives cochées dans le catalogue (A-04, A-06)
            perms_accordees.update({c.lower() for c in codes_cochés})

        # AD ou ADMIN : 6 droits d'administration fixes dans le code (Règle B-04)
        if code_role in (RoleGlobal.ADMIN, "AD") or getattr(role, "code", "") in (RoleGlobal.ADMIN, "AD"):
            perms_accordees.update(DROITS_ADMIN_AD)
            perms_accordees.difference_update(DROITS_ADMIN_RESERVES_DG)
    except Exception:
        pass

    if request:
        request._permissions_effectives_cache = perms_accordees
    return perms_accordees




def permissions_du_role(role, tenant=None) -> set[str]:
    """Renvoie les permissions accordées par un rôle (Règles B-08, B-09)."""
    if not role or not getattr(role, "est_actif", True):
        return set()
    if getattr(role, "code", "") in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
        return set(REGISTRE.keys())

    class _PorteurFictif:
        def __init__(self, r):
            self.role = r
            self.role_global = getattr(r, "code", "")
            self.is_dg = False
            self.is_owner = False
            self.is_authenticated = True
            self.pk = None

    return permissions_effectives(_PorteurFictif(role), tenant=tenant)

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
