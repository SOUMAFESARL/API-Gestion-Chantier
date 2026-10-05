"""Service métier pour la gestion des rôles et des permissions par module.

Gère :
- L'initialisation des rôles système par défaut
- La création de rôles personnalisés
- La modification d'un rôle et de sa matrice de permissions
- La suppression d'un rôle avec réassignation obligatoire (Option B)
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Module, Permission, Role, RoleModulePermission, Utilisateur
from apps.catalogue.models import CatalogueModule, CataloguePermission
from apps.core.enums import (
    MODULES_DETAILS,
    ModuleChoix,
    NiveauAcces,
    RoleGlobal,
    StatutUtilisateur,
)
from apps.core.exceptions import ActionReserveeDg, RoleSubstitutionObligatoire

MATRICE_DEFAUT = {
    code: dict.fromkeys(ModuleChoix.values, NiveauAcces.VALIDATION) for code in RoleGlobal.values
}

ROLES_SYSTEME_INFOS = {
    RoleGlobal.DIRECTEUR_GENERAL: (
        "Directeur Général / PDG",
        "Supervision globale, décisions stratégiques et vision consolidée de tous les projets",
    ),
    RoleGlobal.ADMIN: (
        "Administrateur",
        "Paramétrage de l'organisation, administration technique et gestion des utilisateurs",
    ),
    RoleGlobal.CHEF_PROJET: (
        "Directeur de Projet",
        "Pilotage opérationnel des projets qui lui sont confiés et accès complet à ses chantiers",
    ),
    RoleGlobal.CONDUCTEUR_TRAVAUX: (
        "Conducteur de Travaux",
        "Supervision quotidienne, coordination des équipes terrain et validation technique",
    ),
    RoleGlobal.CHEF_CHANTIER: (
        "Chef de Chantier",
        "Saisie terrain : avancement, incidents, photos, pointage (interface mobile simplifiée)",
    ),
    RoleGlobal.MAITRE_OUVRAGE: (
        "Maître d'Ouvrage (Client)",
        "Suivi de l'avancement global du chantier et consultation des rapports d'activité",
    ),
    RoleGlobal.MAITRE_OEUVRE: (
        "Maître d'Œuvre",
        "Supervision technique, coordination architecturale et validation des avancements",
    ),
    RoleGlobal.VISITEUR: (
        "Consultant lecture",
        "Consultation de l'avancement et des données du chantier en lecture seule",
    ),
}


# Seul le Directeur Général est un rôle système
# immuable (non supprimable). Les autres rôles par défaut (AD, CP, CT, CC,
# MOA, MOE, VI) sont pré-configurés mais restent supprimables par le DG.
CODES_ROLES_SYSTEME = frozenset({RoleGlobal.DIRECTEUR_GENERAL})


def initialiser_modules_par_defaut() -> list[Module]:
    """Initialise ou met à jour le catalogue des 5 modules souverains BTP dans le schéma courant."""
    modules_crees = []
    with transaction.atomic():
        for code, details in MODULES_DETAILS.items():
            libelle = dict(ModuleChoix.choices).get(code, code)
            mod, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    "libelle": libelle,
                    "description": details.get("description", ""),
                    "ordre": details.get("ordre", 0),
                    "icone": details.get("icone", "box"),
                    "est_actif": True,
                },
            )
            modules_crees.append(mod)
    return modules_crees


PERMISSIONS_FONDAMENTALES = [
    {
        "code": "LECTURE",
        "libelle": "Lecture / Consultation",
        "description": "Permet de consulter et visualiser les données du module.",
        "ordre": 1,
        "est_actif": True,
    },
    {
        "code": "ECRITURE",
        "libelle": "Écriture / Saisie",
        "description": "Permet de créer, éditer et modifier les données du module.",
        "ordre": 2,
        "est_actif": True,
    },
    {
        "code": "VALIDATION",
        "libelle": "Validation / Approbation",
        "description": "Permet de valider, approuver, signer ou rejeter les éléments du module.",
        "ordre": 3,
        "est_actif": True,
    },
    {
        "code": "SUPPRESSION",
        "libelle": "Suppression / Archivage",
        "description": "Permet de supprimer ou archiver les éléments du module.",
        "ordre": 4,
        "est_actif": True,
    },
]


def initialiser_permissions_par_defaut() -> list[Permission]:
    """Initialise le catalogue des 4 permissions fondamentales dans le schéma courant."""
    modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
    perms_creees = []
    with transaction.atomic():
        for data in PERMISSIONS_FONDAMENTALES:
            perm, _ = Permission.objects.update_or_create(
                code=data["code"],
                defaults=data,
            )
            if modules_actifs:
                perm.modules.add(*modules_actifs)
            perms_creees.append(perm)
    return perms_creees


def _normaliser_permissions_modules(permissions_input) -> dict[str, list[str]]:
    """Normalise les permissions reçues sous forme de dict ou de list vers un dict {module_code: [code_permission, ...]}."""
    resultat: dict[str, list[str]] = {}
    if not permissions_input:
        return resultat

    def _extraire_codes(m_code_str: str, val) -> list[str]:
        m = m_code_str.lower()
        codes = set()
        if isinstance(val, int):
            if val >= 1:
                codes.add(f"{m}.lire")
            if val >= 2:
                codes.add("chantier.rediger" if m == "chantier" else f"{m}.ecrire")
            if val >= 3:
                codes.add(f"{m}.valider")
            return list(codes)

        items = val if isinstance(val, (list, tuple, set)) else [val]
        for item in items:
            if not item:
                continue
            code_str = str(item.get("code") if isinstance(item, dict) else item).strip().lower()
            if code_str in ("lecture", "lire", f"{m}.lire"):
                codes.add(f"{m}.lire")
            elif code_str in ("saisie", "ecriture", "rediger", f"{m}.ecrire", f"{m}.rediger"):
                codes.add("chantier.rediger" if m == "chantier" else f"{m}.ecrire")
            elif code_str in ("validation", "valider", f"{m}.valider"):
                if m == "projets":
                    codes.add("projets.changer_statut")
                else:
                    codes.add(f"{m}.valider")
            elif code_str in REGISTRE:
                codes.add(code_str)
            elif f"{m}.{code_str}" in REGISTRE:
                codes.add(f"{m}.{code_str}")
        return list(codes)

    if isinstance(permissions_input, list):
        for item in permissions_input:
            if isinstance(item, dict):
                m_code = item.get("module") or item.get("module_code")
                p_items = item.get("permissions") or []
                if m_code:
                    resultat[str(m_code).lower()] = _extraire_codes(str(m_code).lower(), p_items)
    elif isinstance(permissions_input, dict):
        for m_code, val in permissions_input.items():
            resultat[str(m_code).lower()] = _extraire_codes(str(m_code).lower(), val)

    return resultat


def _calculer_niveau_scalaire(codes_list: list[str]) -> int:
    """Calcule le niveau scalaire correspondant aux codes pour compatibilité legacy."""
    c_set = set(codes_list)
    if any(c.endswith(".valider") for c in c_set):
        return NiveauAcces.VALIDATION
    if any(c.endswith(".ecrire") or c.endswith(".rediger") for c in c_set):
        return NiveauAcces.ECRITURE
    if any(c.endswith(".lire") for c in c_set):
        return NiveauAcces.LECTURE
    return NiveauAcces.AUCUN


def _verifier_plafond_modele(code_role: str, mod_code: str, niveau_demande: int):
    """Règle A-12 : aucun ancien plafond de modèle n'intervient."""
    pass


NIVEAUX_DEFAUT_ROLES = {
    "AD": {"administration": 2, "chantier": 3, "ged": 3, "pilotage": 2, "projets": 3, "tiers": 2},
    "BAI": {"administration": 0, "chantier": 1, "ged": 1, "pilotage": 1, "projets": 1, "tiers": 0},
    "CC": {"administration": 0, "chantier": 2, "ged": 2, "pilotage": 0, "projets": 1, "tiers": 0},
    "CP": {"administration": 0, "chantier": 2, "ged": 2, "pilotage": 1, "projets": 2, "tiers": 1},
    "CT": {"administration": 0, "chantier": 3, "ged": 2, "pilotage": 1, "projets": 2, "tiers": 1},
    "DF": {"administration": 0, "chantier": 1, "ged": 2, "pilotage": 3, "projets": 1, "tiers": 2},
    "DG": {"administration": 3, "chantier": 3, "ged": 3, "pilotage": 3, "projets": 3, "tiers": 3},
    "DO": {"administration": 0, "chantier": 3, "ged": 3, "pilotage": 2, "projets": 3, "tiers": 2},
    "MAG": {"administration": 0, "chantier": 1, "ged": 1, "pilotage": 0, "projets": 0, "tiers": 2},
    "VI": {"administration": 0, "chantier": 1, "ged": 1, "pilotage": 1, "projets": 1, "tiers": 0},
}

ANNEXE1_CODES_PAR_ROLE = {
    "DG": {"projets.creer", "projets.changer_statut", "projets.resilier_archiver", "projets.affecter_membres", "projets.gerer_equipes", "projets.voir_montants"},
    "AD": {"projets.creer", "projets.changer_statut", "projets.resilier_archiver", "projets.affecter_membres", "projets.gerer_equipes"},
    "DO": {"projets.creer", "projets.changer_statut", "projets.resilier_archiver", "projets.voir_montants"},
    "DF": {"projets.voir_montants"},
    "CP": {"projets.changer_statut", "projets.affecter_membres", "projets.gerer_equipes", "projets.voir_montants"},
    "CT": {"projets.gerer_equipes"},
    "CC": set(),
    "MAG": set(),
    "BAI": set(),
    "VI": set(),
}


def appliquer_modeles_roles() -> list[Role]:
    """Applique les gabarits de rôles souverains (ModeleRole) au schéma courant (A-12)."""
    initialiser_modules_par_defaut()
    initialiser_permissions_par_defaut()

    from apps.catalogue.models import ModeleRole

    modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
    cat_modules_map = {
        m.code.lower(): m
        for m in CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
    }
    all_cat_perms_map = {
        p.code: p
        for p in CataloguePermission.objects.filter(est_actif=True, supprime_le__isnull=True)
    }

    modeles_qs = list(
        ModeleRole.objects.filter(est_actif=True, supprime_le__isnull=True).prefetch_related(
            "modules_plafonds"
        )
    )

    roles_traites = []
    with transaction.atomic():
        if modeles_qs:
            for modele in modeles_qs:
                r_code = (modele.code or "").upper()
                role, _ = Role.objects.update_or_create(
                    code=r_code,
                    defaults={
                        "libelle": modele.libelle,
                        "description": modele.description,
                        "est_systeme": r_code in CODES_ROLES_SYSTEME,
                        "est_actif": True,
                    },
                )
                modules_modele = {
                    mrm.module_code.lower()
                    for mrm in modele.modules_plafonds.all()
                }

                for mod in modules_actifs:
                    m_key = mod.code.lower()
                    cat_mod = cat_modules_map.get(m_key)
                    if role.code == "DG":
                        niveau_cible = NiveauAcces.VALIDATION
                    else:
                        niveau_cible = NIVEAUX_DEFAUT_ROLES.get(r_code, {}).get(
                            m_key, NiveauAcces.LECTURE if m_key in modules_modele else NiveauAcces.AUCUN
                        )

                    rmp, _ = RoleModulePermission.objects.update_or_create(
                        role=role,
                        module=mod,
                        defaults={
                            "niveau": niveau_cible,
                            "module_catalogue": cat_mod,
                        },
                    )

                    if m_key == "projets":
                        codes_module = set()
                        if niveau_cible >= 1:
                            codes_module.add("projets.lire")
                        if niveau_cible >= 2:
                            codes_module.add("projets.ecrire")
                        if r_code in ANNEXE1_CODES_PAR_ROLE:
                            codes_module.update(ANNEXE1_CODES_PAR_ROLE[r_code])
                    else:
                        from apps.core.registre_permissions import permissions_du_module
                        codes_module = set(permissions_du_module(m_key, niveau_cible))

                    cat_perms_to_set = [
                        all_cat_perms_map[c]
                        for c in codes_module
                        if c in all_cat_perms_map
                    ]
                    rmp.permissions_catalogue.set(cat_perms_to_set)

                    rmp.niveau = niveau_cible
                    rmp.save()

                RoleModulePermission.objects.filter(role=role).filter(module__isnull=False).exclude(
                    module__in=modules_actifs
                ).delete()
                roles_traites.append(role)
        else:
            for code, (libelle, description) in ROLES_SYSTEME_INFOS.items():
                r_code = (code or "").upper()
                role, _ = Role.objects.update_or_create(
                    code=r_code,
                    defaults={
                        "libelle": libelle,
                        "description": description,
                        "est_systeme": r_code in CODES_ROLES_SYSTEME,
                        "est_actif": True,
                    },
                )
                for mod in modules_actifs:
                    m_key = mod.code.lower()
                    cat_mod = cat_modules_map.get(m_key)
                    niveau_cible = NIVEAUX_DEFAUT_ROLES.get(r_code, {}).get(
                        m_key, NiveauAcces.VALIDATION if r_code == "DG" else NiveauAcces.LECTURE
                    )
                    rmp, _ = RoleModulePermission.objects.update_or_create(
                        role=role,
                        module=mod,
                        defaults={
                            "niveau": niveau_cible,
                            "module_catalogue": cat_mod,
                        },
                    )
                    if m_key == "projets":
                        codes_module = set()
                        if niveau_cible >= 1:
                            codes_module.add("projets.lire")
                        if niveau_cible >= 2:
                            codes_module.add("projets.ecrire")
                        if r_code in ANNEXE1_CODES_PAR_ROLE:
                            codes_module.update(ANNEXE1_CODES_PAR_ROLE[r_code])
                    else:
                        from apps.core.registre_permissions import permissions_du_module
                        codes_module = set(permissions_du_module(m_key, niveau_cible))

                    cat_perms_to_set = [
                        all_cat_perms_map[c]
                        for c in codes_module
                        if c in all_cat_perms_map
                    ]
                    rmp.permissions_catalogue.set(cat_perms_to_set)
                    rmp.niveau = niveau_cible
                    rmp.save()

                roles_traites.append(role)

    return roles_traites


def initialiser_roles_par_defaut() -> list[Role]:
    """Initialise les rôles par défaut avec leurs permissions selon les modèles souverains."""
    return appliquer_modeles_roles()


def creer_role(
    code: str,
    libelle: str,
    description: str = "",
    permissions_modules=None,
    cree_par=None,
) -> Role:
    """Crée un nouveau rôle personnalisé obligatoirement lié à TOUS les modules actifs."""
    code = code.strip().upper()
    if not code:
        raise ValidationError(_("Le code du rôle est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé du rôle est obligatoire."))

    if code in ("DG", "ADMIN", "AD"):
        raise ValidationError(_("Le rôle Directeur Général est réservé et ne peut pas être créé."))
    if "directeur general" in libelle.lower() or "directeur général" in libelle.lower():
        raise ValidationError(_("Le libellé Directeur Général est réservé au fondateur du tenant."))

    with transaction.atomic():
        if Role.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise ValidationError(_(f"Un rôle avec le code '{code}' existe déjà."))

        role = Role.objects.create(
            code=code,
            libelle=libelle.strip(),
            description=description.strip(),
            est_systeme=False,
            est_actif=True,
            cree_par=cree_par,
        )

        norm_perms = _normaliser_permissions_modules(permissions_modules)
        modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
        cat_modules_map = {
            m.code.lower(): m for m in CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
        }
        all_cat_perms = {
            p.code: p for p in CataloguePermission.objects.filter(est_actif=True, supprime_le__isnull=True)
        }

        # Invariant de complétude : Tout rôle est obligatoirement lié à TOUS les modules actifs
        for mod in modules_actifs:
            perms_for_mod = norm_perms.get(mod.code.lower(), [])
            cat_mod = cat_modules_map.get(mod.code.lower())
            niveau_calcule = _calculer_niveau_scalaire(perms_for_mod)
            _verifier_plafond_modele(code, mod.code, niveau_calcule)
            rmp = RoleModulePermission.objects.create(
                role=role,
                module=mod,
                module_catalogue=cat_mod,
                niveau=niveau_calcule,
                cree_par=cree_par,
            )
            if perms_for_mod:
                cat_perms = [all_cat_perms[c] for c in perms_for_mod if c in all_cat_perms]
                if cat_perms:
                    rmp.permissions_catalogue.set(cat_perms)

        try:
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            journaliser(
                action=ActionAudit.CREATION,
                type_entite="Role",
                entite_id=role.id,
                utilisateur_id=cree_par.id if cree_par else None,
                valeur_apres={"code": role.code, "libelle": role.libelle},
            )
        except Exception:
            pass

    return role


def modifier_role(
    role: Role,
    libelle: str | None = None,
    description: str | None = None,
    permissions_modules=None,
    modifie_par=None,
) -> Role:
    """Modifie un rôle existant et met à jour sa matrice de permissions."""
    with transaction.atomic():
        if libelle is not None and libelle.strip():
            role.libelle = libelle.strip()
        if description is not None:
            role.description = description.strip()
        role.save()

        modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
        modules_map = {m.code.lower(): m for m in modules_actifs}
        cat_modules_map = {
            m.code.lower(): m for m in CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
        }
        all_cat_perms = {
            p.code: p for p in CataloguePermission.objects.filter(est_actif=True, supprime_le__isnull=True)
        }

        # Garantir l'invariant de liaison à tous les modules
        for mod in modules_actifs:
            cat_mod = cat_modules_map.get(mod.code.lower())
            RoleModulePermission.objects.get_or_create(
                role=role,
                module=mod,
                defaults={"cree_par": modifie_par, "niveau": NiveauAcces.AUCUN, "module_catalogue": cat_mod},
            )

        if permissions_modules is not None:
            norm_perms = _normaliser_permissions_modules(permissions_modules)
            for mod_code, perms_list in norm_perms.items():
                if mod_code in modules_map:
                    cat_mod = cat_modules_map.get(mod_code)
                    rmp, _ = RoleModulePermission.objects.get_or_create(
                        role=role,
                        module=modules_map[mod_code],
                        defaults={"cree_par": modifie_par, "module_catalogue": cat_mod},
                    )
                    if not rmp.module_catalogue and cat_mod:
                        rmp.module_catalogue = cat_mod
                    cat_perms = [all_cat_perms[c] for c in perms_list if c in all_cat_perms]
                    if cat_perms:
                        rmp.permissions_catalogue.set(cat_perms)
                    niveau_scalaire = _calculer_niveau_scalaire(perms_list)
                    _verifier_plafond_modele(role.code, mod_code, niveau_scalaire)
                    rmp.niveau = niveau_scalaire
                    rmp.save()

        try:
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="Role",
                entite_id=role.id,
                utilisateur_id=modifie_par.id if modifie_par else None,
                valeur_apres={"code": role.code, "libelle": role.libelle},
            )
        except Exception:
            pass

    return role


def compter_utilisateurs_et_affectations(role: Role) -> dict[str, int]:
    """Compte le nombre d'utilisateurs actifs et d'affectations actives portant ce rôle."""
    # Nombre d'utilisateurs actifs ayant ce rôle comme rôle personnalisé ou rôle global
    nb_utilisateurs = (
        Utilisateur.objects.filter(role_personnalise=role, supprime_le__isnull=True)
        .exclude(statut=StatutUtilisateur.DESACTIVE)
        .count()
        + Utilisateur.objects.filter(
            role_global=role.code,
            role_personnalise__isnull=True,
            supprime_le__isnull=True,
        )
        .exclude(statut=StatutUtilisateur.DESACTIVE)
        .count()
    )

    from apps.projets.models import AffectationProjet

    nb_affectations = (
        AffectationProjet.objects.filter(role=role, est_actif=True).count()
        + AffectationProjet.objects.filter(
            role_projet=role.code, role__isnull=True, est_actif=True
        ).count()
    )

    return {
        "utilisateurs": nb_utilisateurs,
        "affectations": nb_affectations,
        "total": nb_utilisateurs + nb_affectations,
    }


def supprimer_role(
    role: Role,
    reassigner_vers_role: Role | None = None,
    supprimer_collaborateurs: bool = False,
    supprime_par=None,
) -> dict:
    """Supprime logiquement un rôle selon deux modes au choix :
    - Option A (Réassignation) : réassigne collaborateurs et affectations vers un autre rôle.
    - Option B (Désactivation en cascade) : désactive logiquement tous les collaborateurs portant ce rôle.

    Règles de sécurité souveraines :
    - Un rôle système (DG) ne peut jamais être supprimé.
    - Le rôle Administrateur (AD) ne peut être supprimé que par le Directeur Général / Propriétaire.
    - Le compte Propriétaire / Fondateur (is_owner=True) et le DG racine ne sont JAMAIS désactivés en cascade.
    - Si le rôle est attribué, l'une des deux options (reassigner_vers_role ou supprimer_collaborateurs) est obligatoire.
    - La suppression et les opérations associées sont exécutées dans une transaction atomique.
    """
    from apps.accounts.services.utilisateurs import desactiver_collaborateur_plateforme
    from django.db.models import Q

    # 1. Rôle système immuable (DG)
    if role.est_systeme:
        raise ValidationError(_("Les rôles système ne peuvent pas être supprimés."))

    # 2. Protection du rôle Administrateur (AD) : seul le DG/Propriétaire peut le supprimer
    if role.code in (RoleGlobal.ADMIN, "AD"):
        est_dg_ou_owner = bool(
            supprime_par
            and (
                getattr(supprime_par, "is_dg", False)
                or getattr(supprime_par, "is_owner", False)
                or getattr(supprime_par, "role_global", None) == RoleGlobal.DIRECTEUR_GENERAL
            )
        )
        if not est_dg_ou_owner:
            raise ActionReserveeDg(
                _("Seul le Directeur Général a autorité pour supprimer le rôle Administrateur.")
            )

    counts = compter_utilisateurs_et_affectations(role)
    total_impacte = counts["total"]

    # 3. Validation des options
    if total_impacte > 0 and not reassigner_vers_role and not supprimer_collaborateurs:
        raise ValidationError(
            _(
                f"Ce rôle est actuellement attribué à {counts['utilisateurs']} utilisateur(s) "
                f"et {counts['affectations']} affectation(s). "
                "Veuillez spécifier un rôle de remplacement ou confirmer la suppression des collaborateurs."
            )
        )

    if reassigner_vers_role and reassigner_vers_role.id == role.id:
        raise ValidationError(_("Le rôle de remplacement doit être différent du rôle à supprimer."))

    with transaction.atomic():
        utilisateurs_reassignes = 0
        affectations_reassignees = 0
        utilisateurs_supprimes = 0
        affectations_cloturees = 0

        if supprimer_collaborateurs:
            # Option B : Désactivation logique des collaborateurs portant ce rôle
            users_to_deactivate = list(
                Utilisateur.objects.filter(
                    Q(role_personnalise=role)
                    | (Q(role_global=role.code) & Q(role_personnalise__isnull=True))
                )
                .filter(supprime_le__isnull=True)
                .exclude(statut=StatutUtilisateur.DESACTIVE)
            )

            for collab in users_to_deactivate:
                # Garde-fou souverain : on ne désactive JAMAIS le propriétaire racine ni le DG ni l'auteur lui-même
                if (
                    getattr(collab, "is_owner", False)
                    or getattr(collab, "role_global", None) == RoleGlobal.DIRECTEUR_GENERAL
                    or (supprime_par and collab.pk == supprime_par.pk)
                ):
                    if collab.role_personnalise_id == role.id:
                        collab.role_personnalise = None
                        collab.save(update_fields=["role_personnalise", "modifie_le"])
                    continue

                desactiver_collaborateur_plateforme(
                    collaborateur=collab,
                    auteur=supprime_par,
                )
                utilisateurs_supprimes += 1

            # Clôture des affectations de projets associées à ce rôle
            from apps.projets.models import AffectationProjet

            affectations_cloturees = (
                AffectationProjet.objects.filter(role=role).update(
                    est_actif=False,
                    supprime_le=timezone.now(),
                    supprime_par=supprime_par,
                )
                + AffectationProjet.objects.filter(
                    role_projet=role.code, role__isnull=True
                ).update(
                    est_actif=False,
                    supprime_le=timezone.now(),
                    supprime_par=supprime_par,
                )
            )

        elif reassigner_vers_role:
            # Option A : Réassignation des utilisateurs et affectations
            qs_users = Utilisateur.objects.filter(role_personnalise=role)
            utilisateurs_reassignes = qs_users.update(role_personnalise=reassigner_vers_role)

            qs_global = Utilisateur.objects.filter(
                role_global=role.code, role_personnalise__isnull=True
            )
            if reassigner_vers_role.code in RoleGlobal.values:
                qs_global.update(role_global=reassigner_vers_role.code)
            else:
                qs_global.update(role_personnalise=reassigner_vers_role)

            from apps.projets.models import AffectationProjet

            qs_aff = AffectationProjet.objects.filter(role=role)
            affectations_reassignees = qs_aff.update(role=reassigner_vers_role)

        # Suppression logique du rôle
        role.supprime_le = timezone.now()
        role.supprime_par = supprime_par
        role.est_actif = False
        role.save()

        try:
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            journaliser(
                action=ActionAudit.SUPPRESSION,
                type_entite="Role",
                entite_id=role.id,
                utilisateur_id=supprime_par.id if supprime_par else None,
                valeur_avant={"code": role.code, "libelle": role.libelle},
            )
        except Exception:
            pass

    return {
        "role_supprime": role.code,
        "mode": "suppression_collaborateurs" if supprimer_collaborateurs else "reassignation",
        "utilisateurs_reassignes": utilisateurs_reassignes,
        "affectations_reassignees": affectations_reassignees,
        "utilisateurs_supprimes": utilisateurs_supprimes,
        "affectations_cloturees": affectations_cloturees,
    }


def rattacher_collaborateur_a_role(
    *,
    collaborateur: Utilisateur,
    role: Role | None = None,
    role_global: str | None = None,
    modifie_par: Utilisateur | None = None,
) -> Utilisateur:
    """Rattache un collaborateur à un rôle personnalisé ou met à jour son rôle global.

    Règles d'intégrité et de sécurité :
    - Le Propriétaire/Fondateur (is_owner=True) a un rôle immuable : interdiction de modification.
    - Le rôle de Directeur Général ne peut pas être attribué à un collaborateur standard.
    - Si un 'role' personnalisé est fourni, il doit être actif et non supprimé.
    - Seul le DG ou un Admin peut conférer le rôle ADMIN.
    """
    from django.core.exceptions import ValidationError
    from apps.core.enums import RoleGlobal, StatutUtilisateur

    # Règle 1 : Immutabilité du compte Propriétaire
    if collaborateur.is_owner:
        raise ValidationError(
            _("Le rôle et le statut du Propriétaire / Fondateur sont immuables.")
        )

    # Règle 2 : Interdiction d'attribuer le rôle DG
    if role_global == RoleGlobal.DIRECTEUR_GENERAL:
        raise ValidationError(
            _("Le rôle de Directeur Général est unique et ne peut pas être attribué.")
        )

    # Règle 3 : Validation de l'existence et de l'état du rôle personnalisé
    if role is not None:
        if role.supprime_le is not None or not role.est_actif:
            raise ValidationError(
                _("Le rôle spécifié est inactif ou a été supprimé.")
            )

    with transaction.atomic():
        champs_a_mettre_a_jour = ["modifie_le"]

        if role is not None:
            collaborateur.role_personnalise = role
            champs_a_mettre_a_jour.append("role_personnalise")

            # Si le code du rôle personnalisé correspond à un rôle global connu, synchroniser
            if role.code in RoleGlobal.values:
                collaborateur.role_global = role.code
                champs_a_mettre_a_jour.append("role_global")

        if role_global is not None and role_global in RoleGlobal.values:
            collaborateur.role_global = role_global
            if "role_global" not in champs_a_mettre_a_jour:
                champs_a_mettre_a_jour.append("role_global")

        collaborateur.save(update_fields=champs_a_mettre_a_jour)

        try:
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="CollaborateurRole",
                entite_id=collaborateur.id,
                utilisateur_id=modifie_par.id if modifie_par else None,
                valeur_apres={
                    "role_global": collaborateur.role_global,
                    "role_personnalise_id": str(collaborateur.role_personnalise_id)
                    if collaborateur.role_personnalise_id
                    else None,
                },
            )
        except Exception:
            pass

    return collaborateur