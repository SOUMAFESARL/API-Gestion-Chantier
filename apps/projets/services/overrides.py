"""Service de gestion des surcharges de permissions par projet (Approche Hybride)."""

from apps.accounts.models import Module, Role, RoleModulePermission
from apps.core.enums import NiveauAcces
from apps.projets.models import Projet, ProjetRoleModuleOverride

__all__ = [
    "get_matrice_permissions_projet",
    "set_override_permission_projet",
    "supprimer_override_permission_projet",
]


def _niveau_vers_acces(niveau: int) -> list[str]:
    if niveau == 1:
        return ["lecture"]
    elif niveau == 2:
        return ["lecture", "saisie"]
    elif niveau >= 3:
        return ["lecture", "saisie", "validation"]
    return []


def get_matrice_permissions_projet(projet: Projet) -> list[dict]:
    """Renvoie la matrice complète des rôles actifs et de leurs droits effectifs sur ce projet.

    Pour chaque rôle et chaque module :
    - Si une surcharge existe sur ce projet : niveau = niveau de surcharge, est_surcharge = True
    - Sinon : niveau = niveau par défaut de l'entreprise, est_surcharge = False
    Fournit le champ 'acces' (['lecture', 'saisie', 'validation']) pour l'affichage Next.js.
    """
    roles = Role.objects.filter(est_actif=True, supprime_le__isnull=True).order_by("libelle")
    overrides = {
        (o.role_id, o.module.code): o.niveau
        for o in ProjetRoleModuleOverride.objects.filter(
            projet=projet, supprime_le__isnull=True
        ).select_related("module")
        if o.module and o.module.est_actif
    }
    modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))

    resultat = []
    for role in roles:
        matrice_defaut = {
            p.module.code: p.niveau
            for p in RoleModulePermission.objects.filter(
                role=role, supprime_le__isnull=True
            ).select_related("module")
            if p.module and p.module.est_actif
        }
        modules_droits = {}
        for m in modules_actifs:
            if (role.id, m.code) in overrides:
                niv = overrides[(role.id, m.code)]
                modules_droits[m.code] = {
                    "niveau": niv,
                    "acces": _niveau_vers_acces(niv),
                    "est_surcharge": True,
                }
            else:
                niv = matrice_defaut.get(m.code, NiveauAcces.AUCUN)
                modules_droits[m.code] = {
                    "niveau": niv,
                    "acces": _niveau_vers_acces(niv),
                    "est_surcharge": False,
                }

        resultat.append(
            {
                "role_id": str(role.id),
                "code": role.code,
                "libelle": role.libelle,
                "est_systeme": role.est_systeme,
                "modules": modules_droits,
            }
        )

    return resultat


def set_override_permission_projet(
    projet: Projet,
    role: Role,
    module: str | Module,
    niveau: int,
    modifie_par=None,
) -> ProjetRoleModuleOverride:
    """Applique une surcharge de permission sur un module pour un rôle sur ce projet."""
    if isinstance(module, str):
        module_obj = Module.objects.filter(code__iexact=module, supprime_le__isnull=True).first()
        if not module_obj:
            module_obj = Module.objects.get(code=module)
    else:
        module_obj = module

    override, _ = ProjetRoleModuleOverride.objects.update_or_create(
        projet=projet,
        role=role,
        module=module_obj,
        defaults={"niveau": niveau, "supprime_le": None},
    )
    return override


def supprimer_override_permission_projet(projet: Projet, role: Role, module: str | Module) -> bool:
    """Supprime la surcharge d'un rôle pour rétablir le comportement par défaut de l'entreprise."""
    filtre = {"projet": projet, "role": role, "supprime_le__isnull": True}
    if isinstance(module, str):
        filtre["module__code"] = module
    else:
        filtre["module"] = module

    qs = ProjetRoleModuleOverride.objects.filter(**filtre)
    if qs.exists():
        qs.delete()
        return True
    return False
