"""Services de partage externe temporaire 72 h (F6 tâche 3.9).

Règles métier & isolation D9 :
- Création, consultation de la liste et révocation réservées à AD / DG / DO / CP
  (contrôle cumulatif rôle + affectation projet + `ged.voir_<catégorie>`).
- Expiration exacte à +72 h ; révocation immédiate.
- Résolution publique anonyme (`/api/v1/public/partages/{jeton}/`) via un bloc minimal
  `portee_plateforme(motif="resolution_partage_public_ged")` suivi d'une bascule immédiate
  dans `contexte_entreprise(entreprise_id)`.
- Un lien valide sert toujours la version active courante du document (ex. v3 si publiée
  pendant la fenêtre de 72 h).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import Http404
from django.utils import timezone

from apps.core.contexte import contexte_entreprise, portee_plateforme
from apps.core.enums import ActionAudit
from apps.core.modules_actifs import codes_modules_actifs
from apps.ged.models import DUREE_PARTAGE_HEURES, Document, PartageDocument, VersionDocument
from apps.ged.models.exceptions import PartageExpire
from apps.ged.permissions import peut_partager_document
from apps.ged.services.audit import journaliser_evenement_ged

__all__ = [
    "creer_partage_document",
    "enregistrer_telechargement_partage_public",
    "ouvrir_partage_public",
    "revoquer_partage_document",
]


def creer_partage_document(
    *,
    document: Document,
    utilisateur: Any,
    destinataire: str = "",
    note: str = "",
    request: Any = None,
) -> PartageDocument:
    """Crée un lien de partage externe expirant exactement dans 72 heures."""
    autorise, motif = peut_partager_document(utilisateur, document, request=request)
    if not autorise:
        raise PermissionDenied(motif)

    destinataire_propre = (destinataire or "").strip()[:150]
    note_propre = (note or "").strip()[:500]
    echeance = timezone.now() + timedelta(hours=DUREE_PARTAGE_HEURES)

    with transaction.atomic():
        partage = PartageDocument.objects.create(
            entreprise=document.entreprise,
            document=document,
            destinataire=destinataire_propre,
            note=note_propre,
            expire_le=echeance,
            cree_par=utilisateur,
        )
        details = (
            f"Lien de partage externe 72 h créé pour « {destinataire_propre} »"
            if destinataire_propre
            else "Lien de partage externe 72 h créé"
        )
        journaliser_evenement_ged(
            action=ActionAudit.PARTAGE,
            document=document,
            utilisateur=utilisateur,
            details=details,
            request=request,
            extra={
                "partage_id": str(partage.pk),
                "destinataire": destinataire_propre,
                "expire_le": echeance.isoformat(),
            },
        )

    return partage


def revoquer_partage_document(
    *,
    partage: PartageDocument,
    utilisateur: Any,
    request: Any = None,
) -> PartageDocument:
    """Révoque immédiatement un lien de partage externe et trace l'action au journal."""
    document = partage.document
    autorise, motif = peut_partager_document(utilisateur, document, request=request)
    if not autorise:
        raise PermissionDenied(motif)

    if not partage.revoque:
        maintenant = timezone.now()
        with transaction.atomic():
            partage.revoque = True
            partage.revoque_le = maintenant
            partage.revoque_par = utilisateur
            partage.save(update_fields=["revoque", "revoque_le", "revoque_par", "modifie_le"])
            details = (
                f"Lien de partage externe révoqué ({partage.destinataire})"
                if partage.destinataire
                else "Lien de partage externe révoqué"
            )
            journaliser_evenement_ged(
                action=ActionAudit.REVOCATION_PARTAGE,
                document=document,
                utilisateur=utilisateur,
                details=details,
                request=request,
                extra={"partage_id": str(partage.pk), "destinataire": partage.destinataire},
            )

    return partage


@contextmanager
def ouvrir_partage_public(jeton: str):
    """Résout un jeton public sans JWT en respectant strictement l'isolation D9.

    Yields:
        (partage: PartageDocument, document: Document, version_active: VersionDocument)
        à l'intérieur du `contexte_entreprise` du tenant propriétaire.

    Lève :
        - `Http404` si le jeton est inconnu ;
        - `PartageExpire` (HTTP 410, code `partage_expire`) si le lien est révoqué,
          expiré (> 72 h), si le module GED est fermé pour l'entreprise ou si le
          document / projet parent a été supprimé.
    """
    jeton_propre = (jeton or "").strip()
    if not jeton_propre:
        raise Http404("Lien de partage introuvable.")

    with portee_plateforme(motif="resolution_partage_public_ged"):
        trouve = (
            PartageDocument.objects.filter(jeton=jeton_propre)
            .values("pk", "entreprise_id")
            .first()
        )

    if trouve is None:
        raise Http404("Lien de partage introuvable.")

    with contexte_entreprise(trouve["entreprise_id"]):
        partage = (
            PartageDocument.objects.select_related("entreprise")
            .filter(pk=trouve["pk"])
            .first()
        )
        if partage is None:
            raise Http404("Lien de partage introuvable.")

        if "ged" not in codes_modules_actifs(partage.entreprise):
            raise PartageExpire()

        document = (
            Document.tous_objets.select_related("projet", "entreprise")
            .filter(pk=partage.document_id)
            .first()
        )
        if (
            partage.est_expire
            or document is None
            or document.supprime_le is not None
            or document.projet.supprime_le is not None
        ):
            raise PartageExpire()

        version_active: VersionDocument | None = document.derniere_version
        if version_active is None or not version_active.fichier:
            raise PartageExpire()

        yield partage, document, version_active


def enregistrer_telechargement_partage_public(
    *,
    partage: PartageDocument,
    document: Document,
    version: VersionDocument,
    request: Any = None,
) -> None:
    """Incrémente atomiquement le compteur et journalise le téléchargement externe."""
    PartageDocument.objects.filter(pk=partage.pk).update(
        consultations=models.F("consultations") + 1
    )
    cible = f" ({partage.destinataire})" if partage.destinataire else ""
    journaliser_evenement_ged(
        action=ActionAudit.TELECHARGEMENT,
        document=document,
        utilisateur=None,
        details=f"Téléchargement via lien externe{cible} — {version.numero}",
        request=request,
        extra={
            "externe": True,
            "partage_id": str(partage.pk),
            "destinataire": partage.destinataire,
            "version": version.numero,
        },
    )
