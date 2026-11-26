"""Services métier de gestion documentaire (GED) — CCD Digital (F6).

Responsabilités :
- Dépôt de document initial (Document + VersionDocument v1) + notification + audit
- Ajout de révision/version sans perte (v n+1 avec verrou `select_for_update`)
- Mise à jour contrôlée (épinglage référence autorisé sur auto ; métadonnées sur manuel seul)
- Suppression protégée (refus 422 pour `est_automatique=True`, contrôle AD/CP, révocation partages)
- Ponts automatiques inter-modules (création automatique + liaison traçable)
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.contexte import contexte_entreprise
from apps.core.enums import ActionAudit, TypeEvenementNotification
from apps.ged.models import Document, LiaisonDocument, PartageDocument, VersionDocument
from apps.ged.models.exceptions import (
    DocumentAutomatiqueNonModifiable,
    DocumentAutomatiqueNonSupprimable,
    FormatFichierNonAutorise,
    TailleFichierDepassee,
)
from apps.ged.permissions import peut_supprimer_document
from apps.ged.services.audit import journaliser_evenement_ged
from apps.ged.validators import valider_fichier_ged

logger = logging.getLogger(__name__)

__all__ = [
    "ajouter_version",
    "creer_document_automatique",
    "deposer_document",
    "modifier_document",
    "supprimer_document",
]


def _valider_fichier_avec_exceptions_metier(
    fichier: Any, nom_fichier: str | None = None
) -> dict[str, Any]:
    """Convertit les codes de validation fichier en erreurs métier HTTP adaptées (413 / 400)."""
    try:
        return valider_fichier_ged(fichier, nom_fichier=nom_fichier)
    except ValidationError as exc:
        codes = set()
        if hasattr(exc, "error_list"):
            codes = {getattr(e, "code", None) for e in exc.error_list}
        elif getattr(exc, "code", None):
            codes = {exc.code}

        if "taille_fichier_trop_grande" in codes:
            raise TailleFichierDepassee(str(exc.messages[0]) if exc.messages else None) from exc
        if codes & {
            "extension_manquante",
            "extension_non_autorisee",
            "type_mime_invalide",
            "incoherence_extension_mime",
        }:
            raise FormatFichierNonAutorise(str(exc.messages[0]) if exc.messages else None) from exc
        raise


def _diffuser_notification_ged_apres_commit(
    *,
    entreprise_id: Any,
    projet_id: Any,
    document_id: Any,
    categorie: str,
    auteur_id: Any,
    titre: str,
    message: str,
) -> None:
    """Envoie la notification ciblée hors transaction sans jamais bloquer l'écriture GED."""
    try:
        from apps.accounts.models import Utilisateur
        from apps.notifications.services.dispatch import notifier_projet_par_permission

        with contexte_entreprise(entreprise_id):
            document = Document.objects.select_related("projet").filter(pk=document_id).first()
            if document is None:
                return
            auteur = (
                Utilisateur.objects.filter(pk=auteur_id).first()
                if auteur_id is not None
                else None
            )
            notifier_projet_par_permission(
                projet=document.projet,
                evenement=TypeEvenementNotification.DOCUMENT_DEPOSE,
                permission_requise=f"ged.voir_{categorie.lower()}",
                auteur=auteur,
                objet=document,
                titre=titre[:200],
                message=message,
                lien=f"/projets/{projet_id}/documents",
            )
    except Exception:
        logger.exception(
            "Échec non bloquant de la notification GED (document=%s, projet=%s)",
            document_id,
            projet_id,
        )


def _planifier_notification_ged(
    *,
    projet: Any,
    document: Document,
    auteur: Any,
    titre: str,
    message: str,
) -> None:
    transaction.on_commit(
        partial(
            _diffuser_notification_ged_apres_commit,
            entreprise_id=projet.entreprise_id,
            projet_id=projet.pk,
            document_id=document.pk,
            categorie=document.categorie,
            auteur_id=getattr(auteur, "pk", None),
            titre=titre,
            message=message,
        )
    )


def deposer_document(
    *,
    projet: Any,
    categorie: str,
    fichier: Any,
    nom: str | None = None,
    createur: Any = None,
    est_reference: bool = False,
    description: str = "",
    commentaire: str = "",
    request: Any = None,
    notifier: bool = True,
) -> tuple[Document, VersionDocument]:
    """Dépose un nouveau document dans le classeur GED d'un projet avec sa version initiale v1."""
    if not projet:
        raise ValidationError(_("Un projet valide est requis pour déposer un document."))

    meta = _valider_fichier_avec_exceptions_metier(fichier, nom_fichier=nom)
    nom_fichier_propre = Path(meta["nom"]).name[:255]
    nom_final = (nom or nom_fichier_propre).strip()[:255]

    entreprise = getattr(projet, "entreprise", None)
    if not entreprise:
        raise ValidationError(
            _("Le projet sélectionné n'est rattaché à aucune entreprise valide.")
        )

    with transaction.atomic():
        document = Document.objects.create(
            entreprise=entreprise,
            projet=projet,
            categorie=categorie.upper(),
            nom=nom_final,
            description=(description or "").strip(),
            est_reference=bool(est_reference),
            est_automatique=False,
            createur=createur,
        )

        version = VersionDocument.objects.create(
            entreprise=entreprise,
            document=document,
            numero_version=1,
            fichier=fichier,
            nom_fichier=nom_fichier_propre,
            taille=meta["taille"],
            mime_type=meta["type_mime"],
            hash_sha256=meta["sha256"],
            auteur=createur,
            commentaire=(commentaire or "").strip(),
            est_active=True,
        )

        journaliser_evenement_ged(
            action=ActionAudit.DEPOT,
            document=document,
            utilisateur=createur,
            details=f"Dépôt v1 ({nom_fichier_propre})",
            request=request,
            extra={"version": "v1", "nom_fichier": nom_fichier_propre},
        )

        if notifier:
            _planifier_notification_ged(
                projet=projet,
                document=document,
                auteur=createur,
                titre=f"Nouveau document ({document.categorie}) : {document.nom}",
                message=(
                    f"Le document « {document.nom} » a été déposé sur le chantier {projet.nom}."
                ),
            )

    logger.info(
        "Document GED créé : %s (id=%s, v1, projet=%s, auteur=%s)",
        document.nom,
        document.pk,
        projet.pk,
        getattr(createur, "pk", None),
    )

    return document, version


def ajouter_version(
    *,
    document: Document,
    fichier: Any,
    auteur: Any = None,
    commentaire: str = "",
    est_reference: bool | None = None,
    est_appel_systeme: bool = False,
    exiger_commentaire: bool = False,
    request: Any = None,
    notifier: bool = True,
) -> VersionDocument:
    """Ajoute une révision v(n+1) sans perte à un document existant (F6 §2)."""
    if getattr(document, "est_supprime", False) or document.supprime_le is not None:
        raise ValidationError(
            _("Impossible d'ajouter une version à un document supprimé."),
            code="document_supprime",
        )

    if document.est_automatique and not est_appel_systeme:
        raise DocumentAutomatiqueNonModifiable()

    commentaire_propre = (commentaire or "").strip()
    if exiger_commentaire and not commentaire_propre:
        raise ValidationError(
            {
                "commentaire": _(
                    "La note de révision est obligatoire pour déposer une nouvelle version."
                )
            }
        )

    meta = _valider_fichier_avec_exceptions_metier(fichier)
    nom_fichier_propre = Path(meta["nom"]).name[:255]

    with transaction.atomic():
        doc_verrouille = Document.objects.select_for_update().select_related(
            "projet", "entreprise"
        ).get(pk=document.pk)

        dernier_numero = (
            VersionDocument.tous_objets.filter(document=doc_verrouille).aggregate(
                max_num=models.Max("numero_version")
            )["max_num"]
            or 0
        )
        nouveau_numero = dernier_numero + 1

        VersionDocument.tous_objets.filter(document=doc_verrouille, est_active=True).update(
            est_active=False
        )

        nouvelle_version = VersionDocument.objects.create(
            entreprise=doc_verrouille.entreprise,
            document=doc_verrouille,
            numero_version=nouveau_numero,
            fichier=fichier,
            nom_fichier=nom_fichier_propre,
            taille=meta["taille"],
            mime_type=meta["type_mime"],
            hash_sha256=meta["sha256"],
            auteur=auteur,
            commentaire=commentaire_propre,
            est_active=True,
        )

        champs_maj: list[str] = ["modifie_le"]
        if est_reference is not None and doc_verrouille.est_reference != est_reference:
            doc_verrouille.est_reference = bool(est_reference)
            champs_maj.append("est_reference")
        doc_verrouille.save(update_fields=champs_maj)

        # Synchronise l'instance appelante
        document.est_reference = doc_verrouille.est_reference
        document.modifie_le = doc_verrouille.modifie_le

        details_audit = (
            f"Version v{nouveau_numero} ({nom_fichier_propre}) — {commentaire_propre}"
            if commentaire_propre
            else f"Version v{nouveau_numero} ({nom_fichier_propre})"
        )
        journaliser_evenement_ged(
            action=ActionAudit.NOUVELLE_VERSION,
            document=doc_verrouille,
            utilisateur=auteur,
            details=details_audit,
            request=request,
            extra={"version": f"v{nouveau_numero}", "nom_fichier": nom_fichier_propre},
        )

        if notifier:
            _planifier_notification_ged(
                projet=doc_verrouille.projet,
                document=doc_verrouille,
                auteur=auteur,
                titre=f"Nouvelle version v{nouveau_numero} : {doc_verrouille.nom}",
                message=(
                    f"La version v{nouveau_numero} du document « {doc_verrouille.nom} » "
                    f"est disponible sur le chantier {doc_verrouille.projet.nom}."
                ),
            )

    logger.info(
        "Nouvelle version GED ajoutée : %s (v%d, auteur=%s)",
        document.nom,
        nouveau_numero,
        getattr(auteur, "pk", None),
    )

    return nouvelle_version


def modifier_document(
    *,
    document: Document,
    utilisateur: Any = None,
    est_reference: bool | None = None,
    nom: str | None = None,
    description: str | None = None,
    request: Any = None,
) -> Document:
    """Met à jour un document GED : épinglage sur tout document, métadonnées sur manuel seul."""
    if document.est_automatique and (nom is not None or description is not None):
        raise DocumentAutomatiqueNonModifiable()

    avant = {
        "est_reference": document.est_reference,
        "nom": document.nom,
        "description": document.description,
    }
    champs_maj: list[str] = []
    epinglage_change = False
    meta_change = False

    if est_reference is not None and document.est_reference != bool(est_reference):
        document.est_reference = bool(est_reference)
        champs_maj.append("est_reference")
        epinglage_change = True

    if nom is not None:
        nom_propre = nom.strip()
        if not nom_propre:
            raise ValidationError({"nom": _("Le nom du document ne peut pas être vide.")})
        if document.nom != nom_propre:
            document.nom = nom_propre[:255]
            champs_maj.append("nom")
            meta_change = True

    if description is not None:
        desc_propre = description.strip()
        if document.description != desc_propre:
            document.description = desc_propre
            champs_maj.append("description")
            meta_change = True

    if not champs_maj:
        return document

    champs_maj.append("modifie_le")
    with transaction.atomic():
        document.save(update_fields=champs_maj)
        if epinglage_change:
            details_ep = (
                "Épinglé comme document de référence"
                if document.est_reference
                else "Retiré des documents de référence"
            )
            journaliser_evenement_ged(
                action=ActionAudit.EPINGLAGE,
                document=document,
                utilisateur=utilisateur,
                details=details_ep,
                valeur_avant={"est_reference": avant["est_reference"]},
                extra={"est_reference": document.est_reference},
                request=request,
            )
        if meta_change:
            journaliser_evenement_ged(
                action=ActionAudit.MODIFICATION,
                document=document,
                utilisateur=utilisateur,
                details="Mise à jour des métadonnées du document",
                valeur_avant={"nom": avant["nom"], "description": avant["description"]},
                extra={"nom": document.nom, "description": document.description},
                request=request,
            )

    return document


def supprimer_document(
    *,
    document: Document,
    utilisateur: Any = None,
    motif: str = "",
    request: Any = None,
) -> None:
    """Supprime logiquement un document GED après contrôle d'intégrité et de droits."""
    if getattr(document, "est_automatique", False):
        raise DocumentAutomatiqueNonSupprimable()

    if utilisateur is not None:
        autorise, message_rejet = peut_supprimer_document(utilisateur, document, request=request)
        if not autorise:
            raise PermissionDenied(message_rejet)

    motif_propre = (motif or "").strip()
    maintenant = timezone.now()

    with transaction.atomic():
        document.delete(utilisateur=utilisateur)
        PartageDocument.objects.filter(document=document, revoque=False).update(
            revoque=True,
            revoque_le=maintenant,
            revoque_par=utilisateur
            if utilisateur is not None and getattr(utilisateur, "is_authenticated", True)
            else None,
            modifie_le=maintenant,
        )
        journaliser_evenement_ged(
            action=ActionAudit.SUPPRESSION,
            document=document,
            utilisateur=utilisateur,
            details=motif_propre or "Suppression manuelle du document",
            request=request,
            extra={"motif": motif_propre},
        )

    logger.info(
        "Document GED supprimé logiquement : %s (id=%s, utilisateur=%s, motif=%s)",
        document.nom,
        document.pk,
        getattr(utilisateur, "pk", None),
        motif_propre,
    )


def creer_document_automatique(
    *,
    projet: Any,
    categorie: str,
    fichier: Any,
    source_type: str,
    source_id: Any,
    nom: str | None = None,
    createur: Any = None,
    commentaire: str = "",
    description: str = "",
) -> tuple[Document, VersionDocument, LiaisonDocument]:
    """Point d'entrée pour les ponts automatiques inter-modules (F1, F2, F9)."""
    if not projet:
        raise ValidationError(_("Un projet valide est requis pour le pont automatique."))

    meta = _valider_fichier_avec_exceptions_metier(fichier, nom_fichier=nom)
    nom_fichier_propre = Path(meta["nom"]).name[:255]
    nom_final = (nom or nom_fichier_propre).strip()[:255]

    entreprise = getattr(projet, "entreprise", None)
    if not entreprise:
        raise ValidationError(
            _("Le projet sélectionné n'est rattaché à aucune entreprise valide.")
        )

    with transaction.atomic():
        document = Document.objects.create(
            entreprise=entreprise,
            projet=projet,
            categorie=categorie.upper(),
            nom=nom_final,
            description=description,
            est_reference=False,
            est_automatique=True,
            createur=createur,
        )

        note_version = commentaire or f"Génération automatique depuis {source_type} ({source_id})"
        version = VersionDocument.objects.create(
            entreprise=entreprise,
            document=document,
            numero_version=1,
            fichier=fichier,
            nom_fichier=nom_fichier_propre,
            taille=meta["taille"],
            mime_type=meta["type_mime"],
            hash_sha256=meta["sha256"],
            auteur=createur,
            commentaire=note_version,
            est_active=True,
        )

        liaison = LiaisonDocument.objects.create(
            entreprise=entreprise,
            document=document,
            type_source=str(source_type),
            objet_id=source_id,
        )

        journaliser_evenement_ged(
            action=ActionAudit.DEPOT,
            document=document,
            utilisateur=createur,
            details=f"Archivage automatique ({source_type}) — v1 ({nom_fichier_propre})",
            extra={"source_type": str(source_type), "version": "v1"},
        )

    logger.info(
        "Document automatique GED généré : %s (source=%s, id_source=%s, doc_id=%s)",
        document.nom,
        source_type,
        source_id,
        document.pk,
    )

    return document, version, liaison
