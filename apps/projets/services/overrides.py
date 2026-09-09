"""Service de gestion des surcharges de permissions par projet (Approche Hybride)."""

from apps.accounts.models import Role, RoleModulePermission
from apps.core.enums import ModuleChoix, NiveauAcces
from apps.projets.models import Projet, ProjetRoleModuleOverride

__all__ = [
    "get_matrice_permissions_projet",
    "set_override_permission_projet",
    "supprimer_override_permission_projet",
]


def get_matrice_permissions_projet(projet: Projet) -> list[dict]:
    """Renvoie la matrice complète des rôles actifs et de leurs droits effectifs sur ce projet.

    Pour chaque rôle et chaque module :
    - Si une surcharge existe sur ce projet : niveau = niveau de surcharge, est_surcharge = True
    - Sinon : niveau = niveau par défaut de l'entreprise, est_surcharge = False
    """
    roles = Role.objects.filter(est_actif=True, supprime_le__isnull=True).order_by("libelle")
    overrides = {
        (o.role_id, o.module): o.niveau
        for o in ProjetRoleModuleOverride.objects.filter(projet=projet, supprime_le__isnull=True)
    }

    resultat = []
    for role in roles:
        matrice_defaut = {
            p.module: p.niveau
            for p in RoleModulePermission.objects.filter(role=role, supprime_le__isnull=True)
        }
        modules_droits = {}
        for module in ModuleChoix.values:
            if (role.id, module) in overrides:
                modules_droits[module] = {
                    "niveau": overrides[(role.id, module)],
                    "est_surcharge": True,
                }
            else:
                modules_droits[module] = {
                    "niveau": matrice_defaut.get(module, NiveauAcces.AUCUN),
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
    module: str,
    niveau: int,
    modifie_par=None,
) -> ProjetRoleModuleOverride:
    """Applique une surcharge de permission sur un module pour un rôle sur ce projet."""
    override, _ = ProjetRoleModuleOverride.objects.update_or_create(
        projet=projet,
        role=role,
        module=module,
        defaults={"niveau": niveau, "supprime_le": None},
    )
    return override


def supprimer_override_permission_projet(projet: Projet, role: Role, module: str) -> bool:
    """Supprime la surcharge d'un rôle pour rétablir le comportement par défaut de l'entreprise."""
    qs = ProjetRoleModuleOverride.objects.filter(
        projet=projet, role=role, module=module, supprime_le__isnull=True
    )
    if qs.exists():
        qs.delete()
        return True
    return False
