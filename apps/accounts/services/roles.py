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

# À ce stade de cadrage, tous les rôles disposent temporairement d'un accès complet
# (NiveauAcces.VALIDATION = 3) sur l'intégralité des 12 modules CCD Digital.
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
    RoleGlobal.DIRECTEUR_PROJET: (
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
    RoleGlobal.INGENIEUR_TECHNICIEN: (
        "Ingénieur / Technicien",
        "Contrôle qualité, suivi des non-conformités et vérification des documents techniques",
    ),
    RoleGlobal.RESPONSABLE_FINANCIER: (
        "Responsable Financier",
        "Suivi des budgets, dépenses, situations de paiement et rentabilité",
    ),
    RoleGlobal.DIRECTEUR_FINANCIER: (
        "Directeur Financier",
        "Gestion et validation financière et achats (alias rétrocompatible)",
    ),
    RoleGlobal.RESPONSABLE_ACHATS: (
        "Responsable Achats",
        "Gestion des demandes d'achat, commandes, fournisseurs et livraisons",
    ),
    RoleGlobal.MAGASINIER: (
        "Magasinier",
        "Gestion physique des stocks sur chantier, entrées, sorties et inventaires",
    ),
    RoleGlobal.RESPONSABLE_RH: (
        "Responsable RH",
        "Gestion du personnel, présences, pointages ouvriers, habilitations et incidents",
    ),
    RoleGlobal.SOUS_TRAITANT: (
        "Sous-traitant",
        "Consultation de ses tâches assignées et déclaration d'avancement des travaux",
    ),
    RoleGlobal.FOURNISSEUR: (
        "Fournisseur",
        "Consultation des bons de commande et confirmation des livraisons de matériaux",
    ),
    RoleGlobal.MAITRE_OUVRAGE: (
        "Maître d'Ouvrage (Client)",
        "Suivi de l'avancement global du chantier et consultation des rapports d'activité",
    ),
    RoleGlobal.VISITEUR: (
        "Visiteur",
        "Consultation ponctuelle des chantiers en lecture seule",
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
