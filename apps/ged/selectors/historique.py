"""Selectors d'historique d'audit GED lus depuis `JournalAudit` (source unique immuable)."""

from __future__ import annotations

from typing import Any

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.droits import est_dg
from apps.core.permissions import obtenir_portee_role, obtenir_projets_ids_actifs_utilisateur
from apps.ged.permissions import categories_visibles_utilisateur
from apps.ged.services.audit import ACTION_LIBELLES_GED, TYPE_ENTITE_DOCUMENT_GED

__all__ = [
    "lister_historique_document",
    "lister_historique_global_ged",
]


def _utilisateurs_par_id(ids: set[Any]) -> dict[str, dict[str, str]]:
    """Charge en une seule requête les noms complets des acteurs d'une liste d'audit."""
    ids_propres = [uid for uid in ids if uid is not None]
    if not ids_propres:
        return {}
    utilisateurs = Utilisateur.tous_objets.filter(pk__in=ids_propres).only(
        "id", "prenom", "nom", "email"
    )
    resultat: dict[str, dict[str, str]] = {}
    for user in utilisateurs:
        nom_complet = f"{user.prenom} {user.nom}".strip() or user.email
        resultat[str(user.pk)] = {"id": str(user.pk), "nom_complet": nom_complet}
    return resultat


def _formater_entrees(entrees: list[JournalAudit]) -> list[dict[str, Any]]:
    acteurs = _utilisateurs_par_id({e.utilisateur_id for e in entrees if e.utilisateur_id})
    lignes: list[dict[str, Any]] = []
    for entree in entrees:
        meta = entree.valeur_apres if isinstance(entree.valeur_apres, dict) else {}
        utilisateur = acteurs.get(str(entree.utilisateur_id)) if entree.utilisateur_id else None
        lignes.append(
            {
                "id": str(entree.pk),
                "action": entree.action,
                "action_libelle": ACTION_LIBELLES_GED.get(
                    entree.action, entree.get_action_display()
                ),
                "utilisateur": utilisateur,
                "details": str(meta.get("details") or ""),
                "cree_le": entree.horodatage,
                "document_id": str(entree.entite_id) if entree.entite_id else None,
                "document_nom": str(meta.get("document_nom") or ""),
            }
        )
    return lignes


def lister_historique_document(
    *, document_id: Any, entreprise_id: Any, limite: int = 200
) -> list[dict[str, Any]]:
    """Retourne le journal chronologique décroissant des événements d'un document GED."""
    entrees = list(
        JournalAudit.objects.filter(
            entreprise_id=entreprise_id,
            type_entite=TYPE_ENTITE_DOCUMENT_GED,
            entite_id=document_id,
        ).order_by("-horodatage")[:limite]
    )
    return _formater_entrees(entrees)


def lister_historique_global_ged(
    *,
    user: Any,
    entreprise_id: Any,
    projet_id: str | None = None,
    action: str | None = None,
    request: Any = None,
    limite: int = 200,
) -> list[dict[str, Any]]:
    """Retourne le journal global GED (y compris documents supprimés), borné aux droits du rôle."""
    qs = JournalAudit.objects.filter(
        entreprise_id=entreprise_id,
        type_entite=TYPE_ENTITE_DOCUMENT_GED,
    )

    if action:
        qs = qs.filter(action=action.strip().upper())

    if projet_id:
        qs = qs.filter(valeur_apres__projet_id=str(projet_id))
    elif not (
        getattr(user, "is_superuser", False)
        or est_dg(user)
        or obtenir_portee_role(user) == "ENTREPRISE"
    ):
        projets_ids = [
            str(pid) for pid in obtenir_projets_ids_actifs_utilisateur(user, request=request)
        ]
        if not projets_ids:
            return []
        qs = qs.filter(valeur_apres__projet_id__in=projets_ids)

    if not (getattr(user, "is_superuser", False) or est_dg(user)):
        categories = categories_visibles_utilisateur(user, request=request)
        if not categories:
            return []
        qs = qs.filter(valeur_apres__categorie__in=categories)

    entrees = list(qs.order_by("-horodatage")[:limite])
    return _formater_entrees(entrees)
