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


def _normaliser_permissions_modules(permissions_input) -> dict[str, list[Permission]]:
    """Normalise les permissions reçues sous forme de dict ou de list vers un dict {module_code: [Permission, ...]}."""
    perms_par_code = {p.code.upper(): p for p in Permission.objects.filter(est_actif=True, supprime_le__isnull=True).prefetch_related("modules")}
    perms_par_id = {str(p.id): p for p in Permission.objects.filter(est_actif=True, supprime_le__isnull=True).prefetch_related("modules")}

    EQUIVALENCES_CODES = {
        "SAISIE": "ECRITURE",
        "ECRITURE": "ECRITURE",
        "LECTURE": "LECTURE",
        "VALIDATION": "VALIDATION",
        "SUPPRESSION": "SUPPRESSION",
    }

    def _resoudre_perm(p_key, mod_code):
        if not p_key:
            return None
        cle = str(p_key).strip().upper()
        code_canonique = EQUIVALENCES_CODES.get(cle, cle)
        target = perms_par_code.get(code_canonique) or perms_par_id.get(str(p_key))
        if target and target.modules.exists() and not target.modules.filter(code=mod_code).exists():
            return None
        return target

    resultat: dict[str, list[Permission]] = {}

    if not permissions_input:
        return resultat

    if isinstance(permissions_input, list):
        for item in permissions_input:
            if isinstance(item, dict):
                m_code = item.get("module") or item.get("module_code")
                p_items = item.get("permissions") or []
                if m_code:
                    m_code_str = str(m_code).lower()
                    resolved = []
                    for p in p_items:
                        p_key = p.get("code") if isinstance(p, dict) else str(p)
                        target_perm = _resoudre_perm(p_key, m_code_str)
                        if target_perm and target_perm not in resolved:
                            resolved.append(target_perm)
                    resultat[m_code_str] = resolved
    elif isinstance(permissions_input, dict):
        for m_code, val in permissions_input.items():
            m_code_str = str(m_code).lower()
            if isinstance(val, int):
                resolved = []
                if val == 1 and "LECTURE" in perms_par_code:
                    resolved.append(perms_par_code["LECTURE"])
                elif val == 2:
                    for c in ["LECTURE", "ECRITURE"]:
                        if c in perms_par_code:
                            resolved.append(perms_par_code[c])
                elif val >= 3:
                    for c in ["LECTURE", "ECRITURE", "VALIDATION"]:
                        if c in perms_par_code:
                            resolved.append(perms_par_code[c])
                resultat[m_code_str] = resolved
            elif isinstance(val, str):
                target_perm = _resoudre_perm(val, m_code_str)
                resultat[m_code_str] = [target_perm] if target_perm else []
            elif isinstance(val, (list, tuple, set)):
                resolved = []
                for p in val:
                    p_key = p.get("code") if isinstance(p, dict) else str(p)
                    target_perm = _resoudre_perm(p_key, m_code_str)
                    if target_perm and target_perm not in resolved:
                        resolved.append(target_perm)
                resultat[m_code_str] = resolved

    return resultat


def _calculer_niveau_scalaire(permissions_list: list[Permission]) -> int:
    codes = {p.code for p in permissions_list}
    if "VALIDATION" in codes:
        return NiveauAcces.VALIDATION
    if "ECRITURE" in codes:
        return NiveauAcces.ECRITURE
    if "LECTURE" in codes:
        return NiveauAcces.LECTURE
    return NiveauAcces.AUCUN


def _verifier_plafond_modele(code_role: str, mod_code: str, niveau_demande: int):
    """Vérifie que le niveau demandé ne dépasse pas le plafond défini par le ModeleRole s'il existe."""
    if not code_role or not mod_code:
        return
    try:
        from apps.catalogue.models import ModeleRoleModule

        mrm = ModeleRoleModule.objects.filter(
            modele_role__code=code_role.upper(),
            module_code=mod_code.lower(),
            modele_role__est_actif=True,
            modele_role__supprime_le__isnull=True,
        ).first()
        if mrm is not None and niveau_demande > mrm.niveau_max:
            raise ValidationError(
                _(
                    f"Le niveau d'accès demandé ({niveau_demande}) sur le module '{mod_code}' "
                    f"dépasse le plafond autorisé ({mrm.niveau_max}) pour le modèle de rôle '{code_role.upper()}'."
                )
            )
    except ValidationError:
        raise
    except Exception:
        pass


def appliquer_modeles_roles() -> list[Role]:
    """Applique les gabarits de rôles souverains (ModeleRole) et leurs plafonds au schéma courant."""
    initialiser_modules_par_defaut()
    initialiser_permissions_par_defaut()

    from apps.catalogue.models import ModeleRole

    modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
    cat_modules_map = {
        m.code.lower(): m
        for m in CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
    }
    all_perms_map = {
        p.code: p for p in Permission.objects.filter(est_actif=True, supprime_le__isnull=True)
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
                role, _ = Role.objects.update_or_create(
                    code=modele.code,
                    defaults={
                        "libelle": modele.libelle,
                        "description": modele.description,
                        "est_systeme": modele.code in CODES_ROLES_SYSTEME,
                        "est_actif": True,
                    },
                )
                plafonds = {
                    mrm.module_code.lower(): mrm.niveau_max
                    for mrm in modele.modules_plafonds.all()
                }

                for mod in modules_actifs:
                    m_key = mod.code.lower()
                    cat_mod = cat_modules_map.get(m_key)
                    niveau_cible = plafonds.get(m_key, 0)
                    if role.code == "DG":
                        niveau_cible = NiveauAcces.VALIDATION

                    rmp, _ = RoleModulePermission.objects.update_or_create(
                        role=role,
                        module=mod,
                        defaults={
                            "niveau": niveau_cible,
                            "module_catalogue": cat_mod,
                        },
                    )

                    perms_to_set = []
                    if niveau_cible >= 1 and "LECTURE" in all_perms_map:
                        perms_to_set.append(all_perms_map["LECTURE"])
                    if niveau_cible >= 2 and "ECRITURE" in all_perms_map:
                        perms_to_set.append(all_perms_map["ECRITURE"])
                    if niveau_cible >= 3 and "VALIDATION" in all_perms_map:
                        perms_to_set.append(all_perms_map["VALIDATION"])

                    rmp.permissions.set(perms_to_set)

                    cat_perms_to_set = [
                        all_cat_perms_map[p.code]
                        for p in perms_to_set
                        if p.code in all_cat_perms_map
                    ]
                    if cat_perms_to_set:
                        rmp.permissions_catalogue.set(cat_perms_to_set)

                    rmp.niveau = niveau_cible
                    rmp.save()

                RoleModulePermission.objects.filter(role=role).exclude(
                    module__in=modules_actifs
                ).delete()
                roles_traites.append(role)
        else:
            for code, (libelle, description) in ROLES_SYSTEME_INFOS.items():
                role, _ = Role.objects.update_or_create(
                    code=code,
                    defaults={
                        "libelle": libelle,
                        "description": description,
                        "est_systeme": code in CODES_ROLES_SYSTEME,
                        "est_actif": True,
                    },
                )
                for mod in modules_actifs:
                    cat_mod = cat_modules_map.get(mod.code.lower())
                    rmp, _ = RoleModulePermission.objects.update_or_create(
                        role=role,
                        module=mod,
                        defaults={
                            "niveau": NiveauAcces.VALIDATION if code == "DG" else NiveauAcces.LECTURE,
                            "module_catalogue": cat_mod,
                        },
                    )
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
                rmp.permissions.set(perms_for_mod)
                cat_perms = [all_cat_perms[p.code] for p in perms_for_mod if p.code in all_cat_perms]
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
                    rmp.permissions.set(perms_list)
                    cat_perms = [all_cat_perms[p.code] for p in perms_list if p.code in all_cat_perms]
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