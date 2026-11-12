"""Services métier de gestion documentaire (GED) — CCD Digital (F6 MVP).

Responsabilités :
- Dépôt de document initial (Document + VersionDocument v1)
- Ajout de révision/version sans perte (v n+1, conservation des anciennes versions)
- Suppression protégée (refus absolu pour `est_automatique=True`, contrôle AD/CP)
- Ponts automatiques inter-modules (création automatique + liaison traçable)
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from apps.ged.models import Document, LiaisonDocument, VersionDocument
from apps.ged.models.exceptions import DocumentAutomatiqueNonSupprimable
from apps.ged.permissions import peut_supprimer_document
from apps.ged.validators import valider_fichier_ged

logger = logging.getLogger(__name__)

__all__ = [
    "ajouter_version",
    "creer_document_automatique",
    "deposer_document",
    "supprimer_document",
]


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
) -> tuple[Document, VersionDocument]:
    """Dépose un nouveau document dans le classeur GED d'un projet avec sa version initiale v1.

    Paramètres :
        projet : Instance du modèle Projet.
        categorie : Catégorie métier BTP parmi les 6 validées.
        fichier : Fichier uploadé (FileField, InMemoryUploadedFile, etc.).
        nom : Nom usuel du document (déduit du nom du fichier si omis).
        createur : Utilisateur réalisant le dépôt.
        est_reference : Si True, document épinglé en tête de classeur.
        description : Contexte ou description du document.
        commentaire : Note explicative pour cette première version.

    Retourne :
        (document: Document, version: VersionDocument)
    """
    if not projet:
        raise ValidationError(_("Un projet valide est requis pour déposer un document."))

    # 1. Validation stricte du fichier (taille <= 50 Mo, extension, MIME réel, SHA-256)
    meta = valider_fichier_ged(fichier, nom_fichier=nom)
    nom_final = (nom or getattr(fichier, "name", "") or meta["nom"]).strip()

    entreprise = getattr(projet, "entreprise", None)
    if not entreprise:
        raise ValidationError(
            _("Le projet sélectionné n'est rattaché à aucune entreprise valide.")
        )

    with transaction.atomic():
        # 2. Création de l'entité Document (manuel, est_automatique=False)
        document = Document.objects.create(
            entreprise=entreprise,
            projet=projet,
            categorie=categorie.upper(),
            nom=nom_final,
            description=description,
            est_reference=est_reference,
            est_automatique=False,
            createur=createur,
        )

        # 3. Création de la version initiale v1
        version = VersionDocument.objects.create(
            entreprise=entreprise,
            document=document,
            numero_version=1,
            fichier=fichier,
            taille=meta["taille"],
            mime_type=meta["type_mime"],
            hash_sha256=meta["sha256"],
            auteur=createur,
            commentaire=commentaire,
            est_active=True,
        )

    logger.info(
        "Document GED créé : %s (id=%s, v1, projet=%s, auteur=%s)",
        document.nom,
        document.pk,
        projet.pk,
        getattr(createur, "pk", None),
    )

    # TODO: Appeler notifier_projet_par_permission(...) dès disponibilité de T-02.
    # Exemple d'appel prévu :
    # notifier_projet_par_permission(
    #     projet=projet,
    #     evenement="DOCUMENT_DEPOSE",
    #     permission_requise=f"ged.voir_{categorie.lower()}",
    #     auteur=createur,
    #     objet=document,
    #     titre=f"Nouveau document {categorie} : {document.nom}",
    #     message=f"Le document '{document.nom}' a été déposé dans le projet {projet.nom}.",
    #     lien=f"/projets/{projet.id}/ged/documents/{document.id}",
    # )

    return document, version


def ajouter_version(
    *,
    document: Document,
    fichier: Any,
    auteur: Any = None,
    commentaire: str = "",
    est_reference: bool | None = None,
) -> VersionDocument:
    """Ajoute une révision v(n+1) sans perte à un document existant (F6 §2).

    Les anciennes versions restent intègres et accessibles dans l'historique.
    La nouvelle version devient la version active par défaut.
    """
    if getattr(document, "est_supprime", False) or document.supprime_le is not None:
        raise ValidationError(
            _("Impossible d'ajouter une version à un document supprimé."),
            code="document_supprime",
        )

    # 1. Validation stricte du fichier physique
    meta = valider_fichier_ged(fichier)

    with transaction.atomic():
        # 2. Détermination du prochain numéro de version séquentiel
        dernier_numero = (
            VersionDocument.tous_objets.filter(document=document).aggregate(
                max_num=models.Max("numero_version")
            )["max_num"]
            or 0
        )
        nouveau_numero = dernier_numero + 1

        # 3. Désactivation des anciennes versions
        VersionDocument.tous_objets.filter(document=document, est_active=True).update(
            est_active=False
        )

        # 4. Enregistrement de la nouvelle version active
        nouvelle_version = VersionDocument.objects.create(
            entreprise=document.entreprise,
            document=document,
            numero_version=nouveau_numero,
            fichier=fichier,
            taille=meta["taille"],
            mime_type=meta["type_mime"],
            hash_sha256=meta["sha256"],
            auteur=auteur,
            commentaire=commentaire,
            est_active=True,
        )

        # 5. Mise à jour facultative du statut de référence
        champs_maj: list[str] = ["modifie_le"]
        if est_reference is not None and document.est_reference != est_reference:
            document.est_reference = est_reference
            champs_maj.append("est_reference")
        document.save(update_fields=champs_maj)

    logger.info(
        "Nouvelle version GED ajoutée : %s (v%d, auteur=%s)",
        document.nom,
        nouveau_numero,
        getattr(auteur, "pk", None),
    )

    # TODO: Appeler notifier_projet_par_permission(...) dès disponibilité de T-02.
    # Exemple d'appel prévu :
    # notifier_projet_par_permission(
    #     projet=document.projet,
    #     evenement="DOCUMENT_DEPOSE",
    #     permission_requise=f"ged.voir_{document.categorie.lower()}",
    #     auteur=auteur,
    #     objet=document,
    #     titre=f"Nouvelle version v{nouveau_numero} : {document.nom}",
    #     message=f"La version v{nouveau_numero} du document '{document.nom}' est disponible.",
    #     lien=f"/projets/{document.projet_id}/ged/documents/{document.id}",
    # )

    return nouvelle_version


def supprimer_document(
    *,
    document: Document,
    utilisateur: Any = None,
    motif: str = "",
) -> None:
    """Supprime logiquement un document GED après contrôle d'intégrité et de droits.

    Règles absolues (F6 §5) :
    - Document automatique (`est_automatique=True`) : NON supprimable, même par l'Admin.
    - Document manuel : supprimable uniquement par l'Administrateur (AD) ou le Chef de Projet (CP).
    """
    # 1. Protection absolue contre la suppression de documents automatiques
    if getattr(document, "est_automatique", False):
        raise DocumentAutomatiqueNonSupprimable()

    # 2. Contrôle de l'habilitation utilisateur si fourni
    if utilisateur is not None:
        autorise, message_rejet = peut_supprimer_document(utilisateur, document)
        if not autorise:
            raise PermissionDenied(message_rejet)

    # 3. Suppression logique (Socle Commun §3.1)
    document.delete(utilisateur=utilisateur)

    logger.info(
        "Document GED supprimé logiquement : %s (id=%s, utilisateur=%s, motif=%s)",
        document.nom,
        document.pk,
        getattr(utilisateur, "pk", None),
        motif,
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
    """Point d'entrée pour les ponts automatiques inter-modules (F1, F2, F9).

    Crée un document marqué inaltérable (`est_automatique=True`), sa version v1
    et l'entrée de traçabilité `LiaisonDocument` reliant l'objet source au classeur.
    """
    if not projet:
        raise ValidationError(_("Un projet valide est requis pour le pont automatique."))

    # 1. Validation du fichier physique
    meta = valider_fichier_ged(fichier, nom_fichier=nom)
    nom_final = (nom or getattr(fichier, "name", "") or meta["nom"]).strip()

    entreprise = getattr(projet, "entreprise", None)
    if not entreprise:
        raise ValidationError(
            _("Le projet sélectionné n'est rattaché à aucune entreprise valide.")
        )

    with transaction.atomic():
        # 2. Création du Document automatique (inaltérable)
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

        # 3. Création de la version v1
        note_version = commentaire or f"Génération automatique depuis {source_type} ({source_id})"
        version = VersionDocument.objects.create(
            entreprise=entreprise,
            document=document,
            numero_version=1,
            fichier=fichier,
            taille=meta["taille"],
            mime_type=meta["type_mime"],
            hash_sha256=meta["sha256"],
            auteur=createur,
            commentaire=note_version,
            est_active=True,
        )

        # 4. Création de la liaison source
        liaison = LiaisonDocument.objects.create(
            entreprise=entreprise,
            document=document,
            type_source=str(source_type),
            objet_id=source_id,
        )

    logger.info(
        "Document automatique GED généré : %s (source=%s, id_source=%s, doc_id=%s)",
        document.nom,
        source_type,
        source_id,
        document.pk,
    )

    # TODO: Appeler notifier_projet_par_permission(...) dès disponibilité de T-02.
    # notifier_projet_par_permission(
    #     projet=projet,
    #     evenement="DOCUMENT_DEPOSE",
    #     permission_requise=f"ged.voir_{categorie.lower()}",
    #     auteur=createur,
    #     objet=document,
    #     titre=f"Document automatique généré ({source_type}) : {document.nom}",
    #     message=f"Un document a été généré automatiquement depuis le module {source_type}.",
    #     lien=f"/projets/{projet.id}/ged/documents/{document.id}",
    # )

    return document, version, liaison
