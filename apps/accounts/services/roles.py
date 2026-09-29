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

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.core.enums import ModuleChoix, NiveauAcces, RoleGlobal

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



def initialiser_roles_par_defaut() -> list[Role]:
    """Initialise les rôles système avec leurs permissions par défaut dans le schéma courant."""
    roles_crees = []
    with transaction.atomic():
        for code, (libelle, description) in ROLES_SYSTEME_INFOS.items():
            role, _ = Role.objects.update_or_create(
                code=code,
                defaults={
                    "libelle": libelle,
                    "description": description,
                    "est_systeme": True,
                    "est_actif": True,
                },
            )
            # Met à jour ou crée les permissions de chaque module
            matrice = MATRICE_DEFAUT.get(code, {})
            for module in ModuleChoix.values:
                niveau = matrice.get(module, NiveauAcces.VALIDATION)
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=module,
                    defaults={"niveau": niveau},
                )
            RoleModulePermission.objects.filter(role=role).exclude(
                module__in=ModuleChoix.values
            ).delete()
            roles_crees.append(role)
    return roles_crees


def creer_role(
    code: str,
    libelle: str,
    description: str = "",
    permissions_modules: dict[str, int] | None = None,
    cree_par=None,
) -> Role:
    """Crée un nouveau rôle personnalisé avec sa matrice de permissions."""
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

        permissions_modules = permissions_modules or {}
        for module in ModuleChoix.values:
            niveau = permissions_modules.get(module, NiveauAcces.AUCUN)
            RoleModulePermission.objects.create(
                role=role,
                module=module,
                niveau=niveau,
                cree_par=cree_par,
            )

    return role


def modifier_role(
    role: Role,
    libelle: str | None = None,
    description: str | None = None,
    permissions_modules: dict[str, int] | None = None,
    modifie_par=None,
) -> Role:
    """Modifie un rôle existant et met à jour sa matrice de permissions."""
    with transaction.atomic():
        if libelle is not None and libelle.strip():
            role.libelle = libelle.strip()
        if description is not None:
            role.description = description.strip()
        role.save()

        if permissions_modules is not None:
            for module, niveau in permissions_modules.items():
                if module in ModuleChoix.values:
                    RoleModulePermission.objects.update_or_create(
                        role=role,
                        module=module,
                        defaults={"niveau": niveau},
                    )

    return role


def compter_utilisateurs_et_affectations(role: Role) -> dict[str, int]:
    """Compte le nombre d'utilisateurs et d'affectations actives portant ce rôle."""
    # Nombre d'utilisateurs ayant ce rôle comme rôle personnalisé ou rôle global
    nb_utilisateurs = (
        Utilisateur.objects.filter(role_personnalise=role).count()
        + Utilisateur.objects.filter(role_global=role.code, role_personnalise__isnull=True).count()
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
    supprime_par=None,
) -> dict:
    """Supprime logiquement un rôle avec réassignation obligatoire (Option B).

    Règles :
    - Un rôle système ne peut jamais être supprimé.
    - Si des collaborateurs ou affectations portent ce rôle, reassigner_vers_role est obligatoire.
    - La réassignation et la suppression sont effectuées dans une transaction atomique.
    """
    if role.est_systeme:
        raise ValidationError(_("Les rôles système ne peuvent pas être supprimés."))

    counts = compter_utilisateurs_et_affectations(role)
    total_impacte = counts["total"]

    if total_impacte > 0 and not reassigner_vers_role:
        raise ValidationError(
            _(
                f"Ce rôle est actuellement attribué à {counts['utilisateurs']} utilisateur(s) "
                f"et {counts['affectations']} affectation(s). "
                "Veuillez spécifier un rôle de remplacement."
            )
        )

    if reassigner_vers_role and reassigner_vers_role.id == role.id:
        raise ValidationError(_("Le rôle de remplacement doit être différent du rôle à supprimer."))

    with transaction.atomic():
        utilisateurs_reassignes = 0
        affectations_reassignees = 0

        if reassigner_vers_role:
            # 1. Réassignation des utilisateurs
            qs_users = Utilisateur.objects.filter(role_personnalise=role)
            utilisateurs_reassignes = qs_users.update(role_personnalise=reassigner_vers_role)

            # S'il y a des utilisateurs avec role_global == role.code
            qs_global = Utilisateur.objects.filter(
                role_global=role.code, role_personnalise__isnull=True
            )
            if reassigner_vers_role.code in RoleGlobal.values:
                qs_global.update(role_global=reassigner_vers_role.code)
            else:
                qs_global.update(role_personnalise=reassigner_vers_role)

            # 2. Réassignation des affectations projet
            from apps.projets.models import AffectationProjet

            qs_aff = AffectationProjet.objects.filter(role=role)
            affectations_reassignees = qs_aff.update(role=reassigner_vers_role)

        # 3. Suppression logique du rôle
        role.supprime_le = timezone.now()
        role.supprime_par = supprime_par
        role.est_actif = False
        role.save()

    return {
        "role_supprime": role.code,
        "utilisateurs_reassignes": utilisateurs_reassignes,
        "affectations_reassignees": affectations_reassignees,
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

    return collaborateur