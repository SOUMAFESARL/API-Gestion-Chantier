"""Journalisation unifiée des événements GED dans `JournalAudit` (immuable).

Toute action documentaire (dépôt, consultation, téléchargement, nouvelle version,
épinglage, partage externe, révocation, suppression) passe par `journaliser_evenement_ged`
afin de conserver une source de vérité unique et infalsifiable (Socle Commun §2.4).
"""

from __future__ import annotations

import ipaddress
from typing import Any

from apps.audit.services import journaliser
from apps.core.enums import ActionAudit

__all__ = [
    "ACTIONS_AUDIT_GED",
    "ACTION_LIBELLES_GED",
    "TYPE_ENTITE_DOCUMENT_GED",
    "extraire_meta_requete",
    "journaliser_evenement_ged",
]

TYPE_ENTITE_DOCUMENT_GED = "Document"

ACTION_LIBELLES_GED: dict[str, str] = {
    ActionAudit.CONSULTATION: "Consultation",
    ActionAudit.TELECHARGEMENT: "Téléchargement",
    ActionAudit.DEPOT: "Dépôt",
    ActionAudit.CREATION: "Dépôt",
    ActionAudit.NOUVELLE_VERSION: "Nouvelle version",
    ActionAudit.EPINGLAGE: "Épinglage",
    ActionAudit.MODIFICATION: "Modification",
    ActionAudit.PARTAGE: "Partage externe",
    ActionAudit.REVOCATION_PARTAGE: "Révocation de partage",
    ActionAudit.SUPPRESSION: "Suppression",
}

ACTIONS_AUDIT_GED: tuple[str, ...] = (
    ActionAudit.CONSULTATION,
    ActionAudit.TELECHARGEMENT,
    ActionAudit.DEPOT,
    ActionAudit.NOUVELLE_VERSION,
    ActionAudit.EPINGLAGE,
    ActionAudit.MODIFICATION,
    ActionAudit.PARTAGE,
    ActionAudit.REVOCATION_PARTAGE,
    ActionAudit.SUPPRESSION,
)


def extraire_meta_requete(request: Any) -> tuple[str | None, str]:
    """Extrait proprement l'adresse IP et l'agent utilisateur d'une requête HTTP."""
    if request is None:
        return None, ""

    meta = getattr(request, "META", None) or {}
    xff = (meta.get("HTTP_X_FORWARDED_FOR") or "").strip()
    candidat = xff.split(",")[0].strip() if xff else (meta.get("REMOTE_ADDR") or "").strip()

    adresse_ip: str | None = None
    if candidat:
        try:
            adresse_ip = str(ipaddress.ip_address(candidat))
        except ValueError:
            adresse_ip = None

    appareil = str(meta.get("HTTP_USER_AGENT") or "")[:255]
    return adresse_ip, appareil


def journaliser_evenement_ged(
    *,
    action: str,
    document: Any,
    utilisateur: Any = None,
    details: str = "",
    request: Any = None,
    valeur_avant: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
):
    """Enregistre un événement GED dans la table unique immuable `JournalAudit`.

    Ne jamais passer de jeton de partage ni de secret dans `extra` ou `details`.
    """
    adresse_ip, appareil = extraire_meta_requete(request)
    utilisateur_id = (
        getattr(utilisateur, "pk", None)
        if utilisateur is not None and getattr(utilisateur, "is_authenticated", True)
        else None
    )

    payload: dict[str, Any] = {
        "projet_id": str(document.projet_id),
        "document_nom": document.nom,
        "categorie": document.categorie,
        "details": details,
    }
    if extra:
        payload.update(extra)

    return journaliser(
        action=str(action),
        type_entite=TYPE_ENTITE_DOCUMENT_GED,
        entite_id=document.pk,
        utilisateur_id=utilisateur_id,
        valeur_avant=valeur_avant,
        valeur_apres=payload,
        adresse_ip=adresse_ip,
        appareil=appareil,
    )
