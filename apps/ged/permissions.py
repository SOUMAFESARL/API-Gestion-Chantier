"""Permissions DRF pour le module GED — CCD Digital (F6).

Contrôle d'accès souverain à deux niveaux (Socle Commun §2.3) :
- Niveau 1 : Habilitation par catégorie (§6 de F6_synthese_validee.md).
- Niveau 2 : Affectation active au projet (GardePermissionProjet).

Règles strictes d'intégrité (§5 de F6_synthese_validee.md) :
- Document automatique (`est_automatique=True`) : NON supprimable, par personne (ni AD ni CP).
- Document manuel : suppression autorisée UNIQUEMENT pour l'Administrateur (AD)
  et le Chef de Projet (CP), sous réserve de détenir la permission de suppression
  associée à la catégorie.
"""

from __future__ import annotations

from typing import Any

from rest_framework import permissions

from apps.core.droits import a_permission, est_administrateur, est_dg
from apps.core.enums import RoleGlobal, RoleProjet
from apps.core.permissions import GardePermissionProjet

__all__ = [
    "CATEGORIES_GED",
    "PermissionDocumentParCategorie",
    "PeutConsulterGED",
    "PeutDeposerAdministratif",
    "PeutDeposerContrats",
    "PeutDeposerDivers",
    "PeutDeposerPhotos",
    "PeutDeposerPlans",
    "PeutDeposerRapports",
    "PeutSupprimerAdministratif",
    "PeutSupprimerContrats",
    "PeutSupprimerDivers",
    "PeutSupprimerDocument",
    "PeutSupprimerPhotos",
    "PeutSupprimerPlans",
    "PeutSupprimerRapports",
    "PeutTelechargerDocument",
    "PeutVoirAdministratif",
    "PeutVoirContrats",
    "PeutVoirDivers",
    "PeutVoirPhotos",
    "PeutVoirPlans",
    "PeutVoirRapports",
    "est_administrateur_ou_cp",
    "obtenir_code_permission_categorie",
    "peut_supprimer_document",
]

# Les 6 catégories métier BTP validées (F6)
CATEGORIES_GED: frozenset[str] = frozenset({
    "PLANS",
    "CONTRATS",
    "RAPPORTS",
    "ADMINISTRATIF",
    "PHOTOS",
    "DIVERS",
})


def obtenir_code_permission_categorie(action: str, categorie: str) -> str:
    """Génère le code de permission normalisé pour une action et une catégorie GED.

    Exemples :
    - action='voir', categorie='PLANS' -> 'ged.voir_plans'
    - action='deposer', categorie='CONTRATS' -> 'ged.deposer_contrats'
    - action='supprimer', categorie='PHOTOS' -> 'ged.supprimer_photos'
    """
    cat = (categorie or "").strip().lower()
    act = (action or "").strip().lower()
    return f"ged.{act}_{cat}"


def est_administrateur_ou_cp(user: Any, projet: Any = None) -> bool:
    """Détermine si l'utilisateur possède l'autorité AD ou CP.

    Vérifie :
    1. Superutilisateur ou Directeur Général (DG).
    2. Administrateur plateforme ou entreprise (AD).
    3. Chef de projet (CP) global ou désigné comme chef de projet sur le projet.
    4. Affectation active avec rôle CP sur le projet concerné.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False) or est_dg(user) or est_administrateur(user):
        return True

    role_global = getattr(user, "role_global", "")
    roles_autorises = (
        RoleGlobal.ADMIN,
        RoleGlobal.CHEF_PROJET,
        "AD",
        "CP",
        "ADMIN",
        "CHEF_PROJET",
    )
    if role_global in roles_autorises:
        return True

    role = getattr(user, "role", None)
    if role and getattr(role, "code", "") in ("AD", "CP", "ADMIN", "CHEF_PROJET"):
        return True

    role_perso = getattr(user, "role_personnalise", None)
    if role_perso and getattr(role_perso, "code", "") in ("AD", "CP", "ADMIN", "CHEF_PROJET"):
        return True

    # Vérification contextuelle au projet
    if projet is not None:
        chef_projet_id = getattr(projet, "chef_projet_id", None)
        if chef_projet_id and chef_projet_id == user.pk:
            return True

        # Vérification des affectations actives au projet avec le rôle CP
        from django.apps import apps as registre

        try:
            AffectationProjet = registre.get_model("projets", "AffectationProjet")
            est_cp_affecte = AffectationProjet.objects.filter(
                projet=projet,
                utilisateur=user,
                est_actif=True,
                role_projet__in=(RoleProjet.CHEF_PROJET, "CP", "CHEF_PROJET"),
                supprime_le__isnull=True,
            ).exists()
            if est_cp_affecte:
                return True
        except LookupError:
            pass

    return False


def peut_supprimer_document(user: Any, document: Any, request: Any = None) -> tuple[bool, str]:
    """Applique les règles de gestion d'intégrité et d'habilitation pour la suppression.

    Retourne :
        (autorise: bool, motif_rejet: str)
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False, "Authentification requise."

    # Règle F6 §5 : document automatique NON supprimable, même par l'Admin
    if getattr(document, "est_automatique", False):
        return (
            False,
            "Ce document a été généré automatiquement par le système "
            "(workflow F1, F2 ou F9) et ne peut pas être supprimé.",
        )

    projet = getattr(document, "projet", None)

    # Règle F6 §5 : suppression manuelle réservée à AD ou CP
    if not est_administrateur_ou_cp(user, projet=projet):
        return (
            False,
            "La suppression d'un document est strictement réservée à "
            "l'Administrateur (AD) et au Chef de Projet (CP).",
        )

    # Règle F6 §6 : permission explicite ged.supprimer_<catégorie>
    categorie = getattr(document, "categorie", "")
    code_perm = obtenir_code_permission_categorie("supprimer", categorie)

    # DG et superuser ont tous les droits par conception
    if getattr(user, "is_superuser", False) or est_dg(user):
        return True, ""

    if not a_permission(user, code_perm, request=request):
        return (
            False,
            f"Vous n'avez pas la permission de supprimer des documents "
            f"de la catégorie '{categorie}'.",
        )

    return True, ""


# ---------------------------------------------------------------------------
# Gardes généraux du module GED
# ---------------------------------------------------------------------------
class PeutConsulterGED(GardePermissionProjet):
    """Accès de base en consultation à la GED d'un projet."""

    code_permission = "ged.lire"


class PeutTelechargerDocument(GardePermissionProjet):
    """Autorisation de téléchargement d'un document ou d'une version."""

    code_permission = "ged.telecharger"


# ---------------------------------------------------------------------------
# Garde de suppression stricte
# ---------------------------------------------------------------------------
class PeutSupprimerDocument(GardePermissionProjet):
    """Garde dédié à la suppression d'un document GED (F6 §5).

    Exige :
    1. Appartenance ou gestion du projet rattaché.
    2. Document manuel (`est_automatique=False`).
    3. Rôle AD ou CP.
    4. Permission `ged.supprimer_<catégorie>`.
    """

    message = "Suppression non autorisée pour ce document."

    def has_object_permission(self, request, view, obj) -> bool:
        # Vérification d'accès projet de base
        if not super().has_object_permission(request, view, obj):
            return False

        # Si l'objet est une VersionDocument, on évalue le document parent
        document = getattr(obj, "document", obj)

        autorise, motif = peut_supprimer_document(request.user, document, request=request)
        if not autorise:
            self.message = motif
            return False

        return True


# ---------------------------------------------------------------------------
# Garde unifié par catégorie (matrice §6)
# ---------------------------------------------------------------------------
class PermissionDocumentParCategorie(GardePermissionProjet):
    """Garde dynamique appliquant la matrice de visibilité F6 par catégorie.

    Vérifie l'action HTTP contre la catégorie du document ciblé :
    - GET / HEAD / OPTIONS : ged.voir_<catégorie>
    - POST / PUT / PATCH   : ged.deposer_<catégorie>
    - DELETE               : peut_supprimer_document (AD/CP, non-auto, ged.supprimer_<cat>)
    """

    message = "Vos habilitations ne vous permettent pas d'accéder à ce document."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False) or est_dg(user):
            return True

        # Lors d'une création (POST), on valide la catégorie demandée dans la payload
        if request.method == "POST":
            categorie = (
                request.data.get("categorie")
                if hasattr(request, "data") and isinstance(request.data, dict)
                else None
            )
            if categorie:
                code_perm = obtenir_code_permission_categorie("deposer", categorie)
                if not a_permission(user, code_perm, request=request):
                    self.message = (
                        f"Vous n'avez pas la permission de déposer des documents "
                        f"dans la catégorie '{categorie}'."
                    )
                    return False

        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if not super().has_object_permission(request, view, obj):
            return False

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False) or est_dg(user):
            return True

        document = getattr(obj, "document", obj)
        categorie = getattr(document, "categorie", "")

        # 1. Suppression
        if request.method == "DELETE":
            autorise, motif = peut_supprimer_document(user, document, request=request)
            if not autorise:
                self.message = motif
                return False
            return True

        # 2. Consultation
        if request.method in permissions.SAFE_METHODS:
            code_perm = obtenir_code_permission_categorie("voir", categorie)
            if not a_permission(user, code_perm, request=request):
                self.message = (
                    f"Vous n'avez pas la permission de consulter la catégorie "
                    f"'{categorie}'."
                )
                return False
            return True

        # 3. Modification / Dépôt de version
        code_perm = obtenir_code_permission_categorie("deposer", categorie)
        if not a_permission(user, code_perm, request=request):
            self.message = (
                f"Vous n'avez pas la permission de modifier ou ajouter une version "
                f"dans la catégorie '{categorie}'."
            )
            return False

        return True


# ---------------------------------------------------------------------------
# Classes de permission explicites par catégorie (§6)
# ---------------------------------------------------------------------------
class PeutVoirPlans(GardePermissionProjet):
    code_permission = "ged.voir_plans"


class PeutDeposerPlans(GardePermissionProjet):
    code_permission = "ged.deposer_plans"


class PeutSupprimerPlans(PeutSupprimerDocument):
    code_permission = "ged.supprimer_plans"


class PeutVoirContrats(GardePermissionProjet):
    code_permission = "ged.voir_contrats"


class PeutDeposerContrats(GardePermissionProjet):
    code_permission = "ged.deposer_contrats"


class PeutSupprimerContrats(PeutSupprimerDocument):
    code_permission = "ged.supprimer_contrats"


class PeutVoirRapports(GardePermissionProjet):
    code_permission = "ged.voir_rapports"


class PeutDeposerRapports(GardePermissionProjet):
    code_permission = "ged.deposer_rapports"


class PeutSupprimerRapports(PeutSupprimerDocument):
    code_permission = "ged.supprimer_rapports"


class PeutVoirAdministratif(GardePermissionProjet):
    code_permission = "ged.voir_administratif"


class PeutDeposerAdministratif(GardePermissionProjet):
    code_permission = "ged.deposer_administratif"


class PeutSupprimerAdministratif(PeutSupprimerDocument):
    code_permission = "ged.supprimer_administratif"


class PeutVoirPhotos(GardePermissionProjet):
    code_permission = "ged.voir_photos"


class PeutDeposerPhotos(GardePermissionProjet):
    code_permission = "ged.deposer_photos"


class PeutSupprimerPhotos(PeutSupprimerDocument):
    code_permission = "ged.supprimer_photos"


class PeutVoirDivers(GardePermissionProjet):
    code_permission = "ged.voir_divers"


class PeutDeposerDivers(GardePermissionProjet):
    code_permission = "ged.deposer_divers"


class PeutSupprimerDivers(PeutSupprimerDocument):
    code_permission = "ged.supprimer_divers"
