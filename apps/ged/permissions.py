"""Permissions DRF pour le module GED — CCD Digital (F6).

Contrôle d'accès souverain à deux niveaux (Socle Commun §2.3) :
- Niveau 1 : Habilitations GED par catégorie (`ged.voir_<cat>`, `ged.deposer_<cat>`,
  `ged.supprimer_<cat>`, `ged.lire`, `ged.telecharger`) — SANS exiger `projets.lire/ecrire`
  (afin de ne pas bloquer des profils comme le Magasinier ou le Chef de Chantier).
- Niveau 2 : Affectation active au projet (ou portée ENTREPRISE / DG / superuser),
  contrôlée aussi bien en lecture, en détail qu'au `POST` sur le `projet` du corps.

Règles strictes d'intégrité & gouvernance validées :
- Document automatique (`est_automatique=True`) : NON supprimable par les utilisateurs
  (ni AD ni CP — renvoie `422 document_automatique_non_supprimable` via le service).
- Document manuel : suppression réservée exclusivement à AD / DG / CP + `ged.supprimer_<cat>`.
- Partage externe temporaire (72 h) et consultation du journal d'audit : réservés
  strictement aux profils AD / DG / DO / CP (avec droit de vue sur la catégorie).
- Téléchargement des contrats/OS/avenants depuis Projets (F1) : verrouillé sur `ged.voir_contrats`.
"""

from __future__ import annotations

from typing import Any

from rest_framework import permissions

from apps.core.droits import a_permission, est_administrateur, est_dg
from apps.core.enums import CategorieDocument, RoleGlobal, RoleProjet
from apps.core.permissions import obtenir_portee_role, obtenir_projets_ids_actifs_utilisateur

__all__ = [
    "CATEGORIES_GED",
    "ORDRE_CATEGORIES_GED",
    "PermissionDocumentParCategorie",
    "PeutConsulterGED",
    "PeutDeposerAdministratif",
    "PeutDeposerContrats",
    "PeutDeposerDivers",
    "PeutDeposerPhotos",
    "PeutDeposerPlans",
    "PeutDeposerRapports",
    "PeutGererPartageOuAuditGed",
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
    "categories_visibles_utilisateur",
    "est_administrateur_ou_cp",
    "est_gestionnaire_ged",
    "obtenir_code_permission_categorie",
    "peut_partager_document",
    "peut_supprimer_document",
    "peut_telecharger_contrat_f1",
    "peut_voir_historique_document",
    "verifier_acces_projet_ged",
]

ORDRE_CATEGORIES_GED: tuple[str, ...] = (
    CategorieDocument.PLANS,
    CategorieDocument.CONTRATS,
    CategorieDocument.RAPPORTS,
    CategorieDocument.ADMINISTRATIF,
    CategorieDocument.PHOTOS,
    CategorieDocument.DIVERS,
)

CATEGORIES_GED: frozenset[str] = frozenset(ORDRE_CATEGORIES_GED)

_CODES_ROLES_AD_CP = frozenset(
    {RoleGlobal.ADMIN, RoleGlobal.CHEF_PROJET, "AD", "CP", "ADMIN", "CHEF_PROJET"}
)
_CODES_ROLES_DO = frozenset({"DO", "DIRECTEUR_OPERATIONS"})


def obtenir_code_permission_categorie(action: str, categorie: str) -> str:
    """Génère le code de permission normalisé `ged.<action>_<categorie>`."""
    cat = (categorie or "").strip().lower()
    act = (action or "").strip().lower()
    return f"ged.{act}_{cat}"


def _codes_role_utilisateur(user: Any) -> set[str]:
    """Collecte les codes de rôle (global, rôle rattaché, rôle personnalisé) d'un utilisateur."""
    codes: set[str] = set()
    role_global = getattr(user, "role_global", None)
    if role_global:
        codes.add(str(role_global).upper())
    role = getattr(user, "role", None)
    if role and getattr(role, "code", None):
        codes.add(str(role.code).upper())
    role_perso = getattr(user, "role_personnalise", None)
    if role_perso and getattr(role_perso, "code", None):
        codes.add(str(role_perso.code).upper())
    return codes


def verifier_acces_projet_ged(user: Any, projet_ou_id: Any, request: Any = None) -> bool:
    """Vérifie le niveau 2 (appartenance projet ou portée ENTREPRISE / DG / superuser)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or est_dg(user):
        return True
    if obtenir_portee_role(user) == "ENTREPRISE":
        return True
    if projet_ou_id is None:
        return False

    projet_id = getattr(projet_ou_id, "pk", projet_ou_id)
    projets_ids = obtenir_projets_ids_actifs_utilisateur(user, request=request)
    cible = str(projet_id)
    return any(str(pid) == cible for pid in projets_ids)


def categories_visibles_utilisateur(user: Any, request: Any = None) -> list[str]:
    """Retourne les catégories GED que l'utilisateur a le droit de consulter."""
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if getattr(user, "is_superuser", False) or est_dg(user):
        return list(ORDRE_CATEGORIES_GED)
    return [
        cat
        for cat in ORDRE_CATEGORIES_GED
        if a_permission(user, obtenir_code_permission_categorie("voir", cat), request=request)
    ]


def _est_cp_sur_projet(user: Any, projet: Any) -> bool:
    """Vérifie si l'utilisateur exerce le rôle Chef de Projet sur le projet donné."""
    if projet is None:
        return False
    chef_projet_id = getattr(projet, "chef_projet_id", None)
    if chef_projet_id and str(chef_projet_id) == str(user.pk):
        return True

    from django.apps import apps as registre

    try:
        AffectationProjet = registre.get_model("projets", "AffectationProjet")
        return AffectationProjet.objects.filter(
            projet=projet,
            utilisateur=user,
            est_actif=True,
            role_projet__in=(RoleProjet.CHEF_PROJET, "CP", "CHEF_PROJET"),
            supprime_le__isnull=True,
        ).exists()
    except LookupError:
        return False


def est_administrateur_ou_cp(user: Any, projet: Any = None) -> bool:
    """Détermine si l'utilisateur possède l'autorité AD, DG ou CP."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or est_dg(user) or est_administrateur(user):
        return True
    if _codes_role_utilisateur(user) & _CODES_ROLES_AD_CP:
        return True
    return _est_cp_sur_projet(user, projet)


def est_gestionnaire_ged(user: Any, projet: Any = None) -> bool:
    """Détermine si l'utilisateur appartient aux profils de gouvernance GED : AD / DG / DO / CP."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if est_administrateur_ou_cp(user, projet=projet):
        return True
    return bool(_codes_role_utilisateur(user) & _CODES_ROLES_DO)


def peut_telecharger_contrat_f1(user: Any, request: Any = None) -> bool:
    """Verrouille le téléchargement des pièces contractuelles F1 sur `ged.voir_contrats`."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or est_dg(user):
        return True
    return a_permission(user, "ged.voir_contrats", request=request)


def peut_supprimer_document(
    user: Any,
    document: Any,
    request: Any = None,
    *,
    verifier_automatique: bool = True,
) -> tuple[bool, str]:
    """Applique les règles d'intégrité et d'habilitation pour la suppression d'un document."""
    if not user or not getattr(user, "is_authenticated", False):
        return False, "Authentification requise."

    if verifier_automatique and getattr(document, "est_automatique", False):
        return (
            False,
            "Ce document a été généré automatiquement par le système "
            "(workflow F1, F2 ou F9) et ne peut pas être supprimé.",
        )

    projet = getattr(document, "projet", None)
    projet_id = getattr(document, "projet_id", None) or getattr(projet, "pk", None)

    if not verifier_acces_projet_ged(user, projet_id, request=request):
        return False, "Vous n'êtes pas affecté à ce projet."

    if not est_administrateur_ou_cp(user, projet=projet):
        return (
            False,
            "La suppression d'un document est strictement réservée à "
            "l'Administrateur (AD) et au Chef de Projet (CP).",
        )

    if getattr(user, "is_superuser", False) or est_dg(user):
        return True, ""

    categorie = getattr(document, "categorie", "")
    code_perm = obtenir_code_permission_categorie("supprimer", categorie)
    if not a_permission(user, code_perm, request=request):
        return (
            False,
            f"Vous n'avez pas la permission de supprimer des documents "
            f"de la catégorie '{categorie}'.",
        )

    return True, ""


def peut_partager_document(user: Any, document: Any, request: Any = None) -> tuple[bool, str]:
    """Contrôle le droit de gérer un partage externe 72 h (AD / DG / DO / CP)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False, "Authentification requise."

    projet = getattr(document, "projet", None)
    projet_id = getattr(document, "projet_id", None) or getattr(projet, "pk", None)

    if not verifier_acces_projet_ged(user, projet_id, request=request):
        return False, "Vous n'êtes pas affecté à ce projet."

    if not est_gestionnaire_ged(user, projet=projet):
        return (
            False,
            "Le partage externe temporaire est réservé aux profils "
            "Administrateur, Direction (DG/DO) et Chef de Projet.",
        )

    if getattr(user, "is_superuser", False) or est_dg(user):
        return True, ""

    categorie = getattr(document, "categorie", "")
    code_perm = obtenir_code_permission_categorie("voir", categorie)
    if not a_permission(user, code_perm, request=request):
        return (
            False,
            f"Vous n'avez pas la permission de consulter la catégorie '{categorie}'.",
        )

    return True, ""


def peut_voir_historique_document(
    user: Any,
    *,
    document: Any = None,
    projet: Any = None,
    request: Any = None,
) -> tuple[bool, str]:
    """Contrôle le droit de consulter le journal d'audit GED (AD / DG / DO / CP)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False, "Authentification requise."

    projet_cible = projet or getattr(document, "projet", None)
    projet_id = getattr(document, "projet_id", None) or getattr(projet_cible, "pk", None)

    if projet_id is not None and not verifier_acces_projet_ged(user, projet_id, request=request):
        return False, "Vous n'êtes pas affecté à ce projet."

    if not est_gestionnaire_ged(user, projet=projet_cible):
        return (
            False,
            "La consultation de l'historique des accès et suppressions est réservée "
            "aux profils Administrateur, Direction (DG/DO) et Chef de Projet.",
        )

    if document is not None and not (getattr(user, "is_superuser", False) or est_dg(user)):
        categorie = getattr(document, "categorie", "")
        code_perm = obtenir_code_permission_categorie("voir", categorie)
        if not a_permission(user, code_perm, request=request):
            return (
                False,
                f"Vous n'avez pas la permission de consulter la catégorie '{categorie}'.",
            )

    return True, ""


# ---------------------------------------------------------------------------
# Base souveraine GED (sans dépendance à `projets.lire` / `projets.ecrire`)
# ---------------------------------------------------------------------------
class _GardeBaseGed(permissions.BasePermission):
    """Vérifie une permission GED + l'affectation au projet rattaché."""

    code_permission: str | None = None
    message = "Vos habilitations GED ne vous permettent pas d'effectuer cette action."

    @staticmethod
    def _document_depuis(obj: Any) -> Any:
        return getattr(obj, "document", obj)

    @staticmethod
    def _projet_id_depuis(obj: Any) -> Any:
        doc = getattr(obj, "document", obj)
        if hasattr(doc, "projet_id") and doc.projet_id:
            return doc.projet_id
        if hasattr(doc, "projet") and doc.projet:
            return doc.projet.pk
        if doc.__class__.__name__ == "Projet":
            return doc.pk
        return None

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or est_dg(user):
            return True
        if self.code_permission:
            return a_permission(user, self.code_permission, request=request)
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        projet_id = self._projet_id_depuis(obj)
        if projet_id is not None and not verifier_acces_projet_ged(
            user, projet_id, request=request
        ):
            self.message = "Vous n'êtes pas affecté à ce projet."
            return False
        if user.is_superuser or est_dg(user):
            return True
        if self.code_permission:
            return a_permission(user, self.code_permission, request=request)
        return True


class PeutConsulterGED(_GardeBaseGed):
    """Accès en consultation à la GED (dès `ged.lire` ou une catégorie visible)."""

    code_permission = None

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or est_dg(user):
            return True
        return a_permission(user, "ged.lire", request=request) or bool(
            categories_visibles_utilisateur(user, request=request)
        )


class PeutTelechargerDocument(_GardeBaseGed):
    """Autorisation de téléchargement d'un document (`ged.telecharger` + `ged.voir_<cat>`)."""

    code_permission = "ged.telecharger"
    message = "Vous n'avez pas la permission de télécharger ce document."

    def has_object_permission(self, request, view, obj) -> bool:
        if not super().has_object_permission(request, view, obj):
            return False
        user = request.user
        if user.is_superuser or est_dg(user):
            return True
        document = self._document_depuis(obj)
        categorie = getattr(document, "categorie", "")
        code_voir = obtenir_code_permission_categorie("voir", categorie)
        if not a_permission(user, code_voir, request=request):
            self.message = f"Vous n'avez pas la permission de consulter la catégorie '{categorie}'."
            return False
        return True


class PeutSupprimerDocument(_GardeBaseGed):
    """Garde dédié à la suppression d'un document GED (AD/CP + `ged.supprimer_<cat>`)."""

    message = "Suppression non autorisée pour ce document."

    def has_object_permission(self, request, view, obj) -> bool:
        document = self._document_depuis(obj)
        autorise, motif = peut_supprimer_document(request.user, document, request=request)
        if not autorise:
            self.message = motif
            return False
        return True


class PeutGererPartageOuAuditGed(_GardeBaseGed):
    """Garde strict AD / DG / DO / CP pour les partages 72 h et le journal d'audit GED."""

    message = (
        "Cette action est réservée aux profils Administrateur, Direction (DG/DO) et Chef de Projet."
    )

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return est_gestionnaire_ged(user)

    def has_object_permission(self, request, view, obj) -> bool:
        document = self._document_depuis(obj)
        autorise, motif = peut_partager_document(request.user, document, request=request)
        if not autorise:
            self.message = motif
            return False
        return True


class PermissionDocumentParCategorie(_GardeBaseGed):
    """Garde unifié appliquant la matrice de visibilité F6 par catégorie et par projet.

    - GET / HEAD / OPTIONS : `ged.voir_<catégorie>` (+ accès projet)
    - POST / PUT / PATCH   : `ged.deposer_<catégorie>` (+ accès projet, y compris body `projet`)
    - DELETE               : AD/CP + `ged.supprimer_<catégorie>` (+ accès projet) ; le verrou
      `est_automatique` est évalué dans le service pour renvoyer un `422` explicite.
    """

    message = "Vos habilitations ne vous permettent pas d'accéder à ce document."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or est_dg(user):
            return True

        if request.method in permissions.SAFE_METHODS:
            if a_permission(user, "ged.lire", request=request) or categories_visibles_utilisateur(
                user, request=request
            ):
                return True
            self.message = "Vous n'avez accès à aucune catégorie de la gestion documentaire."
            return False

        if request.method == "POST":
            data = getattr(request, "data", None)
            if data is not None and hasattr(data, "get"):
                categorie = (data.get("categorie") or "").strip().upper()
                if categorie in CATEGORIES_GED:
                    code_perm = obtenir_code_permission_categorie("deposer", categorie)
                    if not a_permission(user, code_perm, request=request):
                        self.message = (
                            f"Vous n'avez pas la permission de déposer des documents "
                            f"dans la catégorie '{categorie}'."
                        )
                        return False

                projet_id = data.get("projet") or data.get("projet_id")
                if projet_id and not verifier_acces_projet_ged(user, projet_id, request=request):
                    self.message = "Vous n'êtes pas affecté à ce projet."
                    return False

        return True

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        document = self._document_depuis(obj)
        projet_id = self._projet_id_depuis(document)
        if projet_id is not None and not verifier_acces_projet_ged(
            user, projet_id, request=request
        ):
            self.message = "Vous n'êtes pas affecté à ce projet."
            return False

        if user.is_superuser or est_dg(user):
            return True

        categorie = getattr(document, "categorie", "")

        if request.method == "DELETE":
            # On contrôle ici l'autorité AD/CP + permission de catégorie ; la protection
            # `est_automatique` lève un 422 (`document_automatique_non_supprimable`) côté service.
            autorise, motif = peut_supprimer_document(
                user,
                document,
                request=request,
                verifier_automatique=False,
            )
            if not autorise:
                self.message = motif
                return False
            return True

        if request.method in permissions.SAFE_METHODS:
            code_perm = obtenir_code_permission_categorie("voir", categorie)
            if not a_permission(user, code_perm, request=request):
                self.message = (
                    f"Vous n'avez pas la permission de consulter la catégorie '{categorie}'."
                )
                return False
            return True

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
class PeutVoirPlans(_GardeBaseGed):
    code_permission = "ged.voir_plans"


class PeutDeposerPlans(_GardeBaseGed):
    code_permission = "ged.deposer_plans"


class PeutSupprimerPlans(PeutSupprimerDocument):
    code_permission = "ged.supprimer_plans"


class PeutVoirContrats(_GardeBaseGed):
    code_permission = "ged.voir_contrats"


class PeutDeposerContrats(_GardeBaseGed):
    code_permission = "ged.deposer_contrats"


class PeutSupprimerContrats(PeutSupprimerDocument):
    code_permission = "ged.supprimer_contrats"


class PeutVoirRapports(_GardeBaseGed):
    code_permission = "ged.voir_rapports"


class PeutDeposerRapports(_GardeBaseGed):
    code_permission = "ged.deposer_rapports"


class PeutSupprimerRapports(PeutSupprimerDocument):
    code_permission = "ged.supprimer_rapports"


class PeutVoirAdministratif(_GardeBaseGed):
    code_permission = "ged.voir_administratif"


class PeutDeposerAdministratif(_GardeBaseGed):
    code_permission = "ged.deposer_administratif"


class PeutSupprimerAdministratif(PeutSupprimerDocument):
    code_permission = "ged.supprimer_administratif"


class PeutVoirPhotos(_GardeBaseGed):
    code_permission = "ged.voir_photos"


class PeutDeposerPhotos(_GardeBaseGed):
    code_permission = "ged.deposer_photos"


class PeutSupprimerPhotos(PeutSupprimerDocument):
    code_permission = "ged.supprimer_photos"


class PeutVoirDivers(_GardeBaseGed):
    code_permission = "ged.voir_divers"


class PeutDeposerDivers(_GardeBaseGed):
    code_permission = "ged.deposer_divers"


class PeutSupprimerDivers(PeutSupprimerDocument):
    code_permission = "ged.supprimer_divers"
