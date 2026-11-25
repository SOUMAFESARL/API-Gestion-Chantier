"""Service d'archivage automatique et idempotent en GED (F6 MVP — tâche 3.4).

Ponts automatiques inter-modules branchés par signaux `post_save` (depuis `apps/ged/signals.py`)
et appelables directement depuis les services métier :

1. Projets (F1) -> `TypeSourceLiaison.F1_CONTRAT`, catégorie `CategorieDocument.CONTRATS` :
   - `ProjetContrat` (`fichier`) : archivage initial ou nouvelle version du contrat du marché
   - `Projet.ordre_service` : ordre de service de démarrage (avec versioning si remplacé)
   - `Avenant` (`document` et `ordre_service`) : document signé + OS de l'avenant
2. Journal de chantier (F2) -> `TypeSourceLiaison.F2_RAPPORT` :
   - `RapportJournalier` au statut `APPROUVE` :
     - Fiche de synthèse PDF (`CategorieDocument.RAPPORTS`) générée via ReportLab ou reçue
     - Photos embarquées dans `JournalChantier.saisie["photos"]` (`CategorieDocument.PHOTOS`)
     - Pièces jointes de `JournalChantier.saisie["pieces_jointes"]` (`CategorieDocument.RAPPORTS`)

Garanties transverses :
- Idempotence stricte via `LiaisonDocument(type_source, objet_id)` + empreinte SHA-256.
- Isolation multi-entreprise D9 garantie via `contexte_entreprise(...)`.
- Isolation des pannes : toute anomalie d'archivage ou de notification est journalisée
  (`logger.exception`) dans un savepoint dédié sans jamais bloquer F1 ni F2.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import re
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.chantier.models import JournalChantier, RapportJournalier
from apps.core.contexte import (
    contexte_entreprise,
    en_portee_plateforme,
    entreprise_courante_id,
)
from apps.core.enums import (
    CategorieDocument,
    StatutRapport,
    TypeEvenementNotification,
    TypeSourceLiaison,
)
from apps.ged.models import Document, LiaisonDocument, VersionDocument
from apps.ged.services.documents import ajouter_version, creer_document_automatique
from apps.ged.validators import EXTENSIONS_AUTORISEES, TAILLE_MAX_FICHIER_OCTETS
from apps.projets.models import Avenant, Element, Projet, ProjetContrat

logger = logging.getLogger(__name__)

__all__ = [
    "archiver_avenant",
    "archiver_avenant_par_id",
    "archiver_contrat_projet",
    "archiver_contrat_projet_par_id",
    "archiver_ordre_service_projet",
    "archiver_ordre_service_projet_par_id",
    "archiver_rapport_approuve",
    "archiver_rapport_approuve_par_id",
    "generer_pdf_synthese_rapport",
]

_PREFIXE_OS_AVENANT = "Ordre de service — "
_PREFIXE_SYNTHESE_RAPPORT = "Rapport journalier — "

_EXTENSIONS_PAR_MIME: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/excel": ".xls",
    "application/x-excel": ".xls",
    "application/x-msexcel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


# ---------------------------------------------------------------------------
# Utilitaires internes : contexte D9, lecture fichiers, déduplication, notifs
# ---------------------------------------------------------------------------


@contextmanager
def _contexte_pour_entreprise(entreprise_ou_id: Any):
    """Garantit qu'un contexte d'entreprise D9 actif enveloppe les requêtes GED."""
    if entreprise_ou_id is None:
        yield
        return
    ent_id = getattr(entreprise_ou_id, "pk", entreprise_ou_id)
    courant = entreprise_courante_id()
    if courant is not None and str(courant) == str(ent_id) and not en_portee_plateforme():
        yield
        return
    with contexte_entreprise(ent_id):
        yield


def _normaliser_nom_fichier(nom: str, extension_secours: str = "") -> str:
    """Nettoie un nom de fichier et garantit une extension compatible GED."""
    nom_base = Path(str(nom or "document")).name.strip() or "document"
    ext = Path(nom_base).suffix.lower()
    if ext == ".jepg":
        ext = ".jpeg"
    ext_sec = (extension_secours or "").lower()
    if ext_sec == ".jepg":
        ext_sec = ".jpeg"

    if ext in EXTENSIONS_AUTORISEES:
        stem = Path(nom_base).stem or "document"
    elif ext_sec in EXTENSIONS_AUTORISEES:
        stem = nom_base
        ext = ext_sec
    else:
        stem = Path(nom_base).stem or "document"
        if not ext:
            ext = ext_sec

    stem_propre = re.sub(r"[^\w\-.]+", "_", stem).strip("._") or "document"
    longueur_max_stem = max(20, 180 - len(ext))
    return f"{stem_propre[:longueur_max_stem]}{ext}"


def _lire_fieldfile_en_content_file(
    field_file: Any,
    *,
    nom_prefere: str = "",
    nom_secours: str = "document",
) -> tuple[ContentFile, str] | None:
    """Lit un `FieldFile` depuis son stockage (ex. `StockageContrats`) vers un `ContentFile`.

    Retourne `(ContentFile, sha256)` ou `None` si le fichier est absent/illisible/hors quota.
    """
    if not field_file or not getattr(field_file, "name", ""):
        return None

    try:
        storage = getattr(field_file, "storage", None)
        if storage is not None and not storage.exists(field_file.name):
            logger.warning(
                "Fichier source introuvable sur le stockage lors de l'archivage GED : %s",
                field_file.name,
            )
            return None

        try:
            taille_declaree = getattr(field_file, "size", None)
        except Exception:
            taille_declaree = None
        if taille_declaree is not None and (
            taille_declaree <= 0 or taille_declaree > TAILLE_MAX_FICHIER_OCTETS
        ):
            logger.warning(
                "Fichier source hors limites de taille GED (%s octets) : %s",
                taille_declaree,
                field_file.name,
            )
            return None

        field_file.open("rb")
        try:
            octets = field_file.read()
        finally:
            field_file.close()
    except Exception:
        logger.exception(
            "Impossible de lire le fichier source pour archivage GED : %s",
            getattr(field_file, "name", "?"),
        )
        return None

    if not octets or len(octets) > TAILLE_MAX_FICHIER_OCTETS:
        logger.warning(
            "Contenu vide ou supérieur à 50 Mo ignoré à l'archivage GED : %s",
            getattr(field_file, "name", "?"),
        )
        return None

    ext_stockage = Path(field_file.name).suffix.lower()
    if ext_stockage == ".jepg":
        ext_stockage = ".jpeg"
    ext_pref = Path(nom_prefere).suffix.lower() if nom_prefere else ""
    if ext_pref == ".jepg":
        ext_pref = ".jpeg"

    nom_brut = nom_prefere or Path(field_file.name).name or nom_secours
    nom_final = _normaliser_nom_fichier(nom_brut, extension_secours=ext_stockage or ext_pref)
    sha256 = hashlib.sha256(octets).hexdigest()
    return ContentFile(octets, name=nom_final), sha256


def _lire_fichier_generique_en_content_file(
    fichier: Any,
    *,
    nom_defaut: str,
) -> tuple[ContentFile, str] | None:
    """Convertit une source (`bytes`, `ContentFile`, `UploadedFile`, `FieldFile`)
    en `(ContentFile, sha256)`.
    """
    if fichier is None:
        return None

    if hasattr(fichier, "storage") and getattr(fichier, "name", ""):
        return _lire_fieldfile_en_content_file(
            fichier, nom_prefere=nom_defaut, nom_secours=nom_defaut
        )

    if isinstance(fichier, bytes | bytearray):
        octets = bytes(fichier)
        nom_brut = nom_defaut
    elif hasattr(fichier, "read"):
        if hasattr(fichier, "seek"):
            fichier.seek(0)
        octets = fichier.read()
        if hasattr(fichier, "seek"):
            fichier.seek(0)
        nom_brut = getattr(fichier, "name", "") or nom_defaut
    else:
        return None

    if not octets or len(octets) > TAILLE_MAX_FICHIER_OCTETS:
        return None

    nom_final = _normaliser_nom_fichier(
        nom_brut, extension_secours=Path(nom_defaut).suffix or ".pdf"
    )
    sha256 = hashlib.sha256(octets).hexdigest()
    return ContentFile(octets, name=nom_final), sha256


def _decoder_data_uri(valeur: Any) -> tuple[str, bytes] | None:
    """Décode une data URI `data:<mime>;base64,<contenu>` (ou un chemin de stockage local)."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None

    brut = valeur.strip()
    if brut.startswith("data:") and "," in brut:
        entete, contenu_b64 = brut.split(",", 1)
        if ";base64" not in entete:
            return None
        mime = entete[5:].split(";", 1)[0].strip().lower()
        try:
            octets = base64.b64decode(contenu_b64, validate=True)
        except (ValueError, binascii.Error):
            logger.warning("Payload base64 invalide ignoré lors de l'archivage GED.")
            return None
        if not octets:
            return None
        return mime, octets

    # Repli si un chemin relatif sur default_storage était stocké
    try:
        if default_storage.exists(brut):
            with default_storage.open(brut, "rb") as f:
                octets = f.read()
            if not octets:
                return None
            ext = Path(brut).suffix.lower()
            mime_par_ext = {
                ".pdf": "application/pdf",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            return mime_par_ext.get(ext, "application/octet-stream"), octets
    except Exception:
        logger.warning("Chemin média introuvable ou illisible pour archivage GED : %s", brut)

    return None


def _convertir_webp_si_necessaire(mime: str, octets: bytes) -> tuple[str, bytes]:
    """Convertit une image WEBP (acceptée en F2) en PNG (accepté par les validateurs GED F6)."""
    if mime != "image/webp":
        return mime, octets
    try:
        from PIL import Image

        with Image.open(BytesIO(octets)) as img:
            tampon = BytesIO()
            img.save(tampon, format="PNG")
            return "image/png", tampon.getvalue()
    except Exception:
        logger.exception("Échec de conversion WEBP -> PNG lors de l'archivage GED.")
        return mime, octets


def _version_par_hash_existe(document: Document, sha256: str) -> VersionDocument | None:
    """Retourne la version existante d'un document correspondant à l'empreinte SHA-256."""
    return (
        VersionDocument.objects.filter(
            document=document,
            hash_sha256=sha256,
            supprime_le__isnull=True,
        )
        .order_by("-numero_version")
        .first()
    )


def _assurer_liaison(
    *,
    document: Document,
    type_source: str,
    objet_id: Any,
    entreprise_id: Any,
    createur: Any = None,
) -> LiaisonDocument:
    """Garantit la liaison active `(document, type_source, objet_id)` sans doublon."""
    liaison = LiaisonDocument.tous_objets.filter(
        document=document,
        type_source=str(type_source),
        objet_id=objet_id,
    ).first()
    if liaison is not None:
        if liaison.supprime_le is not None:
            liaison.restaurer()
        return liaison
    return LiaisonDocument.objects.create(
        entreprise_id=entreprise_id,
        document=document,
        type_source=str(type_source),
        objet_id=objet_id,
        cree_par=createur,
    )


def _notifier_document_archive(
    *,
    projet: Projet,
    document: Document,
    auteur: Any = None,
    titre: str,
    message: str,
    regroupement: str | None = None,
) -> None:
    """Diffuse une notification groupée non bloquante après archivage automatique GED."""
    try:
        from apps.notifications.services.dispatch import notifier_projet_par_permission

        with transaction.atomic():
            notifier_projet_par_permission(
                projet=projet,
                evenement=TypeEvenementNotification.DOCUMENT_DEPOSE,
                permission_requise=f"ged.voir_{document.categorie.lower()}",
                auteur=auteur,
                objet=document,
                titre=titre[:200],
                message=message,
                lien=f"/projets/{projet.pk}/documents",
                regroupement=regroupement[:100] if regroupement else None,
            )
    except Exception:
        logger.exception(
            "Échec non bloquant de la notification GED pour le document %s (projet=%s)",
            document.pk,
            projet.pk,
        )


def _archiver_dans_document(
    *,
    projet: Projet,
    categorie: str,
    content_file: ContentFile,
    sha256: str,
    source_type: str,
    source_id: Any,
    nom_document: str,
    createur: Any,
    description: str,
    commentaire: str,
    document_existant: Document | None = None,
    maj_nom_si_different: bool = False,
    cle_regroupement_notif: str | None = None,
) -> tuple[Document, VersionDocument, LiaisonDocument, bool]:
    """Crée ou met à jour un document automatique GED de façon atomique et idempotente.

    Retourne `(document, version, liaison, modifie_ou_cree)`.
    """
    nom_final = (nom_document or content_file.name)[:255]

    with transaction.atomic():
        if document_existant is not None:
            liaison = _assurer_liaison(
                document=document_existant,
                type_source=source_type,
                objet_id=source_id,
                entreprise_id=projet.entreprise_id,
                createur=createur,
            )
            version_existante = _version_par_hash_existe(document_existant, sha256)
            if version_existante is not None:
                if maj_nom_si_different and document_existant.nom != nom_final:
                    document_existant.nom = nom_final
                    document_existant.save(update_fields=["nom", "modifie_le"])
                return document_existant, version_existante, liaison, False

            nouvelle_version = ajouter_version(
                document=document_existant,
                fichier=content_file,
                auteur=createur,
                commentaire=commentaire,
            )
            if maj_nom_si_different and document_existant.nom != nom_final:
                document_existant.nom = nom_final
                document_existant.save(update_fields=["nom", "modifie_le"])
            doc_resultat = document_existant
            ver_resultat = nouvelle_version
            est_nouvelle_version = True
        else:
            doc_resultat, ver_resultat, liaison = creer_document_automatique(
                projet=projet,
                categorie=categorie,
                fichier=content_file,
                source_type=source_type,
                source_id=source_id,
                nom=nom_final,
                createur=createur,
                commentaire=commentaire,
                description=description,
            )
            est_nouvelle_version = False

    if est_nouvelle_version:
        titre_notif = f"Nouvelle version GED ({doc_resultat.categorie}) : {doc_resultat.nom}"
        msg_notif = (
            f"La version v{ver_resultat.numero_version} du document « {doc_resultat.nom} » "
            f"a été archivée automatiquement sur le chantier {projet.nom}."
        )
    else:
        titre_notif = f"Document archivé en GED ({doc_resultat.categorie}) : {doc_resultat.nom}"
        msg_notif = (
            f"Le document « {doc_resultat.nom} » a été archivé automatiquement "
            f"dans la GED du chantier {projet.nom}."
        )

    _notifier_document_archive(
        projet=projet,
        document=doc_resultat,
        auteur=createur,
        titre=titre_notif,
        message=msg_notif,
        regroupement=cle_regroupement_notif,
    )
    return doc_resultat, ver_resultat, liaison, True


# ---------------------------------------------------------------------------
# Pont 1 : Projets (F1) -> CategorieDocument.CONTRATS / F1_CONTRAT
# ---------------------------------------------------------------------------


def archiver_contrat_projet(
    contrat: ProjetContrat,
) -> tuple[Document, VersionDocument, LiaisonDocument] | None:
    """Archive automatiquement un `ProjetContrat` en GED (`CONTRATS`, source `F1_CONTRAT`).

    Idempotent :
    - Si `contrat.pk` possède déjà une liaison vers un document GED contenant la même empreinte
      SHA-256, aucune écriture n'est effectuée.
    - Si un contrat antérieur du même projet possède déjà un document automatique dans `CONTRATS`,
      rattache ce contrat en tant que nouvelle version (`v2`, `v3`...) et crée la liaison dédiée.
    """
    if not contrat or getattr(contrat, "supprime_le", None) is not None or not contrat.fichier:
        return None
    entreprise_id = getattr(contrat, "entreprise_id", None)
    if not entreprise_id or not getattr(contrat, "projet_id", None):
        return None

    try:
        with _contexte_pour_entreprise(entreprise_id):
            lu = _lire_fieldfile_en_content_file(
                contrat.fichier,
                nom_prefere=contrat.nom or "",
                nom_secours=f"contrat_v{contrat.version}",
            )
            if lu is None:
                return None
            content_file, sha256 = lu

            projet = contrat.projet
            base_nom = (
                contrat.nom_sans_extension
                or Path(content_file.name).stem
                or contrat.nom
                or f"v{contrat.version}"
            ).strip()
            titre_doc = f"Contrat du marché — {base_nom}"[:255]

            # 1. Liaison déjà existante pour ce ProjetContrat précis
            liaison_contrat = (
                LiaisonDocument.objects.select_related("document")
                .filter(
                    type_source=TypeSourceLiaison.F1_CONTRAT,
                    objet_id=contrat.pk,
                    supprime_le__isnull=True,
                    document__supprime_le__isnull=True,
                )
                .first()
            )
            doc_existant = liaison_contrat.document if liaison_contrat else None

            # 2. Sinon, vérifier si une version antérieure du contrat de ce projet existe en GED
            if doc_existant is None:
                autres_contrats_ids = list(
                    ProjetContrat.tous_objets.filter(projet_id=contrat.projet_id)
                    .exclude(pk=contrat.pk)
                    .values_list("id", flat=True)
                )
                if autres_contrats_ids:
                    liaison_prec = (
                        LiaisonDocument.objects.select_related("document")
                        .filter(
                            type_source=TypeSourceLiaison.F1_CONTRAT,
                            objet_id__in=autres_contrats_ids,
                            supprime_le__isnull=True,
                            document__projet_id=contrat.projet_id,
                            document__categorie=CategorieDocument.CONTRATS,
                            document__est_automatique=True,
                            document__supprime_le__isnull=True,
                        )
                        .order_by("-cree_le")
                        .first()
                    )
                    if liaison_prec is not None:
                        doc_existant = liaison_prec.document

            doc, ver, liaison, _ = _archiver_dans_document(
                projet=projet,
                categorie=CategorieDocument.CONTRATS,
                content_file=content_file,
                sha256=sha256,
                source_type=TypeSourceLiaison.F1_CONTRAT,
                source_id=contrat.pk,
                nom_document=titre_doc,
                createur=contrat.cree_par,
                description=(
                    f"Contrat du marché (version {contrat.version}) archivé automatiquement "
                    f"depuis la fiche projet {projet.reference}."
                ),
                commentaire=(
                    f"Contrat du marché v{contrat.version} — "
                    f"{contrat.nom or content_file.name}"
                ),
                document_existant=doc_existant,
                maj_nom_si_different=bool(contrat.est_actif),
                cle_regroupement_notif=f"ged_f1_contrat_{projet.pk}",
            )
            return doc, ver, liaison
    except Exception:
        logger.exception(
            "Échec non bloquant de l'archivage GED pour ProjetContrat %s",
            getattr(contrat, "pk", None),
        )
        return None


def archiver_contrat_projet_par_id(contrat_id: Any, entreprise_id: Any) -> None:
    """Point d'entrée différé (`on_commit`) pour archiver un `ProjetContrat` par identifiant."""
    if not contrat_id or not entreprise_id:
        return
    try:
        with _contexte_pour_entreprise(entreprise_id):
            contrat = (
                ProjetContrat.objects.select_related("projet", "cree_par")
                .filter(pk=contrat_id, supprime_le__isnull=True)
                .first()
            )
            if contrat is not None:
                archiver_contrat_projet(contrat)
    except Exception:
        logger.exception(
            "Échec non bloquant dans archiver_contrat_projet_par_id (contrat=%s)",
            contrat_id,
        )


def archiver_ordre_service_projet(
    projet: Projet,
) -> tuple[Document, VersionDocument, LiaisonDocument] | None:
    """Archive automatiquement `Projet.ordre_service` en GED (`CONTRATS`, source `F1_CONTRAT`).

    Idempotent sur `(F1_CONTRAT, projet.pk)` + hash SHA-256 : en cas de remplacement de l'OS de
    démarrage, ajoute une nouvelle version (`v2`, `v3`...) sur le document GED existant.
    """
    if not projet or getattr(projet, "supprime_le", None) is not None or not projet.ordre_service:
        return None
    entreprise_id = getattr(projet, "entreprise_id", None)
    if not entreprise_id:
        return None

    try:
        with _contexte_pour_entreprise(entreprise_id):
            lu = _lire_fieldfile_en_content_file(
                projet.ordre_service,
                nom_prefere=projet.ordre_service_nom or "",
                nom_secours=f"ordre_service_{projet.reference}",
            )
            if lu is None:
                return None
            content_file, sha256 = lu

            liaison_existante = (
                LiaisonDocument.objects.select_related("document")
                .filter(
                    type_source=TypeSourceLiaison.F1_CONTRAT,
                    objet_id=projet.pk,
                    supprime_le__isnull=True,
                    document__supprime_le__isnull=True,
                    document__categorie=CategorieDocument.CONTRATS,
                )
                .first()
            )
            doc_existant = liaison_existante.document if liaison_existante else None

            titre_doc = f"Ordre de service de démarrage — {projet.reference}"[:255]
            doc, ver, liaison, _ = _archiver_dans_document(
                projet=projet,
                categorie=CategorieDocument.CONTRATS,
                content_file=content_file,
                sha256=sha256,
                source_type=TypeSourceLiaison.F1_CONTRAT,
                source_id=projet.pk,
                nom_document=titre_doc,
                createur=projet.cree_par,
                description=(
                    f"Ordre de service de démarrage du chantier {projet.reference} ({projet.nom})."
                ),
                commentaire=(
                    f"Ordre de service de démarrage — "
                    f"{projet.ordre_service_nom or content_file.name}"
                ),
                document_existant=doc_existant,
                cle_regroupement_notif=f"ged_f1_os_{projet.pk}",
            )
            return doc, ver, liaison
    except Exception:
        logger.exception(
            "Échec non bloquant de l'archivage GED de l'ordre de service pour Projet %s",
            getattr(projet, "pk", None),
        )
        return None


def archiver_ordre_service_projet_par_id(projet_id: Any, entreprise_id: Any) -> None:
    """Point d'entrée différé (`on_commit`) pour archiver `Projet.ordre_service`."""
    if not projet_id or not entreprise_id:
        return
    try:
        with _contexte_pour_entreprise(entreprise_id):
            projet = (
                Projet.objects.select_related("entreprise", "cree_par")
                .filter(pk=projet_id, supprime_le__isnull=True)
                .first()
            )
            if projet is not None and projet.ordre_service:
                archiver_ordre_service_projet(projet)
    except Exception:
        logger.exception(
            "Échec non bloquant dans archiver_ordre_service_projet_par_id (projet=%s)",
            projet_id,
        )


def archiver_avenant(
    avenant: Avenant,
) -> list[tuple[Document, VersionDocument, LiaisonDocument]]:
    """Archive le document signé et l'ordre de service d'un `Avenant` en GED (`CONTRATS`).

    Deux documents GED distincts peuvent partager `(F1_CONTRAT, avenant.pk)` car la contrainte
    d'unicité `uq_liaison_doc_source_obj` inclut `document`. Ils sont différenciés par le préfixe
    `"Ordre de service — "` afin que des contenus identiques ou des révisions indépendantes
    restent strictement idempotents.
    """
    resultats: list[tuple[Document, VersionDocument, LiaisonDocument]] = []
    if not avenant or getattr(avenant, "supprime_le", None) is not None:
        return resultats
    entreprise_id = getattr(avenant, "entreprise_id", None)
    if not entreprise_id or not getattr(avenant, "projet_id", None):
        return resultats
    if not avenant.document and not avenant.ordre_service:
        return resultats

    try:
        with _contexte_pour_entreprise(entreprise_id):
            projet = avenant.projet
            liaisons_existantes = list(
                LiaisonDocument.objects.select_related("document")
                .filter(
                    type_source=TypeSourceLiaison.F1_CONTRAT,
                    objet_id=avenant.pk,
                    supprime_le__isnull=True,
                    document__supprime_le__isnull=True,
                    document__categorie=CategorieDocument.CONTRATS,
                )
                .order_by("cree_le")
            )

            doc_avenant_existant = next(
                (
                    liaison.document
                    for liaison in liaisons_existantes
                    if not liaison.document.nom.startswith(_PREFIXE_OS_AVENANT)
                ),
                None,
            )
            doc_os_existant = next(
                (
                    liaison.document
                    for liaison in liaisons_existantes
                    if liaison.document.nom.startswith(_PREFIXE_OS_AVENANT)
                ),
                None,
            )

            cle_notif = f"ged_f1_avenant_{avenant.pk}"

            # 1. Document signé de l'avenant
            if avenant.document:
                try:
                    lu_doc = _lire_fieldfile_en_content_file(
                        avenant.document,
                        nom_prefere=avenant.document_nom or "",
                        nom_secours=f"avenant_{avenant.numero}",
                    )
                    if lu_doc is not None:
                        cf_doc, sha_doc = lu_doc
                        nom_doc = (
                            f"Avenant {avenant.numero} — "
                            f"{avenant.document_nom or 'Document signé'}"
                        )[:255]
                        doc, ver, liaison, _ = _archiver_dans_document(
                            projet=projet,
                            categorie=CategorieDocument.CONTRATS,
                            content_file=cf_doc,
                            sha256=sha_doc,
                            source_type=TypeSourceLiaison.F1_CONTRAT,
                            source_id=avenant.pk,
                            nom_document=nom_doc,
                            createur=avenant.cree_par,
                            description=(
                                f"Avenant n° {avenant.numero} signé le "
                                f"{avenant.date_signature:%d/%m/%Y} — {avenant.objet}"
                            ),
                            commentaire=f"Document signé de l'avenant {avenant.numero}",
                            document_existant=doc_avenant_existant,
                            cle_regroupement_notif=cle_notif,
                        )
                        resultats.append((doc, ver, liaison))
                except Exception:
                    logger.exception(
                        "Échec non bloquant archivage document signé de l'avenant %s",
                        avenant.pk,
                    )

            # 2. Ordre de service de l'avenant
            if avenant.ordre_service:
                try:
                    lu_os = _lire_fieldfile_en_content_file(
                        avenant.ordre_service,
                        nom_prefere=avenant.ordre_service_nom or "",
                        nom_secours=f"ordre_service_avenant_{avenant.numero}",
                    )
                    if lu_os is not None:
                        cf_os, sha_os = lu_os
                        nom_os = f"{_PREFIXE_OS_AVENANT}Avenant {avenant.numero}"[:255]
                        doc, ver, liaison, _ = _archiver_dans_document(
                            projet=projet,
                            categorie=CategorieDocument.CONTRATS,
                            content_file=cf_os,
                            sha256=sha_os,
                            source_type=TypeSourceLiaison.F1_CONTRAT,
                            source_id=avenant.pk,
                            nom_document=nom_os,
                            createur=avenant.cree_par,
                            description=(
                                f"Ordre de service lié à l'avenant n° {avenant.numero} "
                                f"du chantier {projet.reference}."
                            ),
                            commentaire=(
                                f"Ordre de service — Avenant {avenant.numero} "
                                f"({avenant.ordre_service_nom or cf_os.name})"
                            ),
                            document_existant=doc_os_existant,
                            cle_regroupement_notif=cle_notif,
                        )
                        resultats.append((doc, ver, liaison))
                except Exception:
                    logger.exception(
                        "Échec non bloquant archivage OS de l'avenant %s",
                        avenant.pk,
                    )
    except Exception:
        logger.exception(
            "Échec non bloquant de l'archivage GED pour Avenant %s",
            getattr(avenant, "pk", None),
        )

    return resultats


def archiver_avenant_par_id(avenant_id: Any, entreprise_id: Any) -> None:
    """Point d'entrée différé (`on_commit`) pour archiver un `Avenant`."""
    if not avenant_id or not entreprise_id:
        return
    try:
        with _contexte_pour_entreprise(entreprise_id):
            avenant = (
                Avenant.objects.select_related("projet", "cree_par")
                .filter(pk=avenant_id, supprime_le__isnull=True)
                .first()
            )
            if avenant is not None:
                archiver_avenant(avenant)
    except Exception:
        logger.exception(
            "Échec non bloquant dans archiver_avenant_par_id (avenant=%s)",
            avenant_id,
        )


# ---------------------------------------------------------------------------
# Pont 2 : Journal de chantier (F2) -> CategorieDocument.PHOTOS & RAPPORTS
# ---------------------------------------------------------------------------


def _nom_utilisateur(utilisateur: Any) -> str:
    if not utilisateur:
        return "Système"
    nom_complet = f"{getattr(utilisateur, 'prenom', '')} {getattr(utilisateur, 'nom', '')}".strip()
    return nom_complet or getattr(utilisateur, "email", "") or "Utilisateur"


def generer_pdf_synthese_rapport(
    rapport: RapportJournalier,
    journal: JournalChantier | None = None,
) -> bytes:
    """Génère une fiche de synthèse PDF minimale et propre pour un rapport approuvé (ReportLab)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    tampon = BytesIO()
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 13

    def p(texte: Any, style: str = "Normal") -> Paragraph:
        return Paragraph(escape(str(texte or "")).replace("\n", "<br/>"), styles[style])

    projet = rapport.projet
    entreprise = getattr(projet, "entreprise", None)
    saisie = journal.saisie if journal and isinstance(journal.saisie, dict) else {}

    couleur_brute = getattr(entreprise, "couleur_primaire", "") or "#D4652A"
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", couleur_brute):
        couleur_brute = "#D4652A"
    couleur_accent = colors.HexColor(couleur_brute)

    contenu: list[Any] = [
        p("RAPPORT JOURNALIER DE CHANTIER", "Title"),
        p(
            f"{projet.reference} — {projet.nom} | Journée du {rapport.date_rapport:%d/%m/%Y}",
            "Heading2",
        ),
        Spacer(1, 3 * mm),
    ]

    # Tableau d'en-tête synthétique
    localisation = ", ".join(filter(None, [projet.ville, projet.quartier])) or "—"
    meteo_txt = rapport.get_meteo_display()
    meteo_saisie = saisie.get("meteo") if isinstance(saisie.get("meteo"), dict) else None
    if meteo_saisie and any(meteo_saisie.values()):
        morceaux = [
            f"Matin : {meteo_saisie.get('matin') or '—'}",
            f"Après-midi : {meteo_saisie.get('apres_midi') or '—'}",
        ]
        if meteo_saisie.get("conditions"):
            morceaux.append(f"Conditions : {meteo_saisie['conditions']}")
        meteo_txt = " | ".join(morceaux)

    horaires_txt = "—"
    if saisie.get("heure_debut") or saisie.get("heure_fin"):
        horaires_txt = f"{saisie.get('heure_debut') or '?'} -> {saisie.get('heure_fin') or '?'}"

    valide_le_txt = (
        timezone.localtime(rapport.valide_le).strftime("%d/%m/%Y %H:%M")
        if rapport.valide_le
        else "—"
    )

    lignes_entete = [
        [p("<b>Entreprise</b>"), p(getattr(entreprise, "raison_sociale", "—"))],
        [p("<b>Chantier</b>"), p(f"{projet.reference} — {projet.nom}")],
        [p("<b>Localisation</b>"), p(localisation)],
        [p("<b>Date du rapport</b>"), p(f"{rapport.date_rapport:%d/%m/%Y}")],
        [p("<b>Statut</b>"), p(f"{rapport.get_statut_display()} (le {valide_le_txt})")],
        [p("<b>Rédacteur</b>"), p(_nom_utilisateur(rapport.auteur))],
        [p("<b>Approuvé par</b>"), p(_nom_utilisateur(rapport.valide_par))],
        [p("<b>Horaires / Météo</b>"), p(f"{horaires_txt} | {meteo_txt}")],
        [p("<b>Effectif présent</b>"), p(f"{rapport.effectif_present} personne(s)")],
    ]
    tableau_entete = Table(lignes_entete, colWidths=[45 * mm, 125 * mm])
    tableau_entete.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("LINEABOVE", (0, 0), (-1, 0), 1.5, couleur_accent),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    contenu.append(tableau_entete)
    contenu.append(Spacer(1, 5 * mm))

    # Arrêt de chantier éventuel
    arret = saisie.get("arret")
    if isinstance(arret, dict) and arret.get("motif"):
        contenu.append(p("Arrêt de chantier déclaré", "Heading3"))
        contenu.append(p(f"Motif : {arret.get('motif')} — {arret.get('precision') or ''}"))
        contenu.append(Spacer(1, 3 * mm))

    # Observations / Note de fin de journée
    note = (saisie.get("note_redacteur") or rapport.observations or "").strip()
    if note:
        contenu.append(p("Observations et faits marquants", "Heading3"))
        contenu.append(p(note))
        contenu.append(Spacer(1, 4 * mm))

    # Activités réalisées (si saisie structurée disponible)
    activites = [a for a in (saisie.get("activites") or []) if isinstance(a, dict)]
    if activites:
        ids_act = [a["activite_id"] for a in activites if a.get("activite_id")]
        libelles_act: dict[str, tuple[str, str]] = {}
        if ids_act:
            try:
                for pk, lib, unite in Element.objects.filter(pk__in=ids_act).values_list(
                    "pk", "libelle", "unite"
                ):
                    libelles_act[str(pk)] = (lib, unite or "")
            except Exception:
                libelles_act = {}

        lignes_travaux = [
            [p("<b>Tâche / Activité</b>"), p("<b>Mesure du jour</b>"), p("<b>Observation</b>")]
        ]
        for a in activites:
            aid = str(a.get("activite_id") or "")
            libelle, unite = libelles_act.get(aid, (aid or "Activité", ""))
            if a.get("pourcentage_jour") is not None:
                mesure = f"{a['pourcentage_jour']} %"
            elif a.get("jalon_atteint"):
                mesure = "Jalon atteint"
            elif a.get("quantite_jour") is not None:
                mesure = f"{a['quantite_jour']} {unite}".strip()
            else:
                mesure = "—"
            lignes_travaux.append([p(libelle), p(mesure), p(a.get("observation") or "—")])

        contenu.append(p("Travaux déclarés", "Heading3"))
        tableau_travaux = Table(lignes_travaux, colWidths=[75 * mm, 35 * mm, 60 * mm])
        tableau_travaux.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        contenu.append(tableau_travaux)
        contenu.append(Spacer(1, 4 * mm))

    # Incidents / Blocages / Médias résumés
    nb_photos = len(saisie.get("photos") or [])
    nb_incidents = len(saisie.get("incidents") or [])
    nb_blocages = len(saisie.get("blocages") or []) or int(rapport.blocages_critiques or 0)
    if nb_photos or nb_incidents or nb_blocages:
        contenu.append(p("Indicateurs complémentaires", "Heading3"))
        contenu.append(
            p(
                f"Incidents déclarés : {nb_incidents} | "
                f"Blocages : {nb_blocages} | "
                f"Photos jointes : {nb_photos}"
            )
        )
        contenu.append(Spacer(1, 4 * mm))

    # Signatures
    signatures = [s for s in (getattr(journal, "signatures", None) or []) if isinstance(s, dict)]
    if signatures:
        contenu.append(p("Circuit d'approbation", "Heading3"))
        lignes_sig = [
            [p("<b>Étape</b>"), p("<b>Signataire</b>"), p("<b>Date</b>"), p("<b>Commentaire</b>")]
        ]
        for sig in signatures:
            lignes_sig.append(
                [
                    p(sig.get("etape") or "—"),
                    p(sig.get("nom") or "—"),
                    p(str(sig.get("signe_le") or "—")[:19].replace("T", " ")),
                    p(sig.get("commentaire") or "—"),
                ]
            )
        tab_sig = Table(lignes_sig, colWidths=[30 * mm, 45 * mm, 35 * mm, 60 * mm])
        tab_sig.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        contenu.append(tab_sig)
        contenu.append(Spacer(1, 4 * mm))
    elif rapport.commentaire_validation:
        contenu.append(p("Commentaire d'approbation", "Heading3"))
        contenu.append(p(rapport.commentaire_validation))
        contenu.append(Spacer(1, 4 * mm))

    contenu.append(
        p(
            "<i>Document généré et archivé automatiquement en GED — CCD Digital.</i>",
            "Normal",
        )
    )

    doc = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Rapport journalier {projet.reference} {rapport.date_rapport:%Y-%m-%d}",
    )
    doc.build(contenu)
    return tampon.getvalue()


def archiver_rapport_approuve(
    rapport: RapportJournalier,
    fichier_pdf: Any = None,
) -> dict[str, Any]:
    """Archive en GED un `RapportJournalier` approuvé (F2 -> F6).

    Paramètres :
        rapport : Instance `RapportJournalier` au statut `StatutRapport.APPROUVE`.
        fichier_pdf : PDF optionnel fourni par un générateur serveur externe (`bytes`,
            `ContentFile`, `UploadedFile`, `FieldFile` ou flux binaire). Si `None`, génère
            une fiche de synthèse PDF minimale via `generer_pdf_synthese_rapport` (ReportLab).

    Archivage effectué (`source_type=TypeSourceLiaison.F2_RAPPORT`, `source_id=rapport.pk`) :
    - Fiche PDF de synthèse dans `CategorieDocument.RAPPORTS`
    - Photos embarquées dans `JournalChantier.saisie["photos"]` dans `CategorieDocument.PHOTOS`
    - Pièces jointes de `JournalChantier.saisie["pieces_jointes"]` dans `CategorieDocument.RAPPORTS`
    """
    bilan: dict[str, Any] = {
        "rapport": None,
        "photos": [],
        "pieces_jointes": [],
    }
    if not rapport or getattr(rapport, "supprime_le", None) is not None:
        return bilan
    if rapport.statut != StatutRapport.APPROUVE:
        return bilan

    entreprise_id = getattr(rapport, "entreprise_id", None)
    if not entreprise_id or not getattr(rapport, "projet_id", None):
        return bilan

    try:
        with _contexte_pour_entreprise(entreprise_id):
            projet = rapport.projet
            journal = JournalChantier.objects.filter(
                rapport_id=rapport.pk,
                supprime_le__isnull=True,
            ).first()
            saisie = journal.saisie if journal and isinstance(journal.saisie, dict) else {}
            cle_notif = f"ged_f2_{rapport.pk}"

            # Préchargement des liaisons et empreintes existantes pour garantir l'idempotence
            liaisons_existantes = list(
                LiaisonDocument.objects.select_related("document")
                .filter(
                    type_source=TypeSourceLiaison.F2_RAPPORT,
                    objet_id=rapport.pk,
                    supprime_le__isnull=True,
                    document__supprime_le__isnull=True,
                )
                .order_by("cree_le")
            )
            docs_existants = [liaison.document for liaison in liaisons_existantes]
            docs_photos_ids = [
                d.pk for d in docs_existants if d.categorie == CategorieDocument.PHOTOS
            ]
            docs_rapports_ids = [
                d.pk for d in docs_existants if d.categorie == CategorieDocument.RAPPORTS
            ]

            hashes_photos: set[str] = set()
            if docs_photos_ids:
                hashes_photos = set(
                    VersionDocument.objects.filter(
                        document_id__in=docs_photos_ids,
                        supprime_le__isnull=True,
                    ).values_list("hash_sha256", flat=True)
                )

            hashes_rapports: set[str] = set()
            if docs_rapports_ids:
                hashes_rapports = set(
                    VersionDocument.objects.filter(
                        document_id__in=docs_rapports_ids,
                        supprime_le__isnull=True,
                    ).values_list("hash_sha256", flat=True)
                )

            doc_synthese_existant = next(
                (
                    d
                    for d in docs_existants
                    if d.categorie == CategorieDocument.RAPPORTS
                    and d.nom.startswith(_PREFIXE_SYNTHESE_RAPPORT)
                ),
                None,
            )

            # 1. Archivage du PDF de synthèse du rapport approuvé (RAPPORTS)
            try:
                auteur_rapport = rapport.valide_par or rapport.auteur
                nom_synthese = (
                    f"{_PREFIXE_SYNTHESE_RAPPORT}{projet.reference} — "
                    f"{rapport.date_rapport:%d/%m/%Y}"
                )[:255]
                nom_fichier_pdf = _normaliser_nom_fichier(
                    f"rapport_journalier_{projet.reference}_{rapport.date_rapport:%Y%m%d}.pdf",
                    extension_secours=".pdf",
                )

                if fichier_pdf is not None:
                    lu_pdf = _lire_fichier_generique_en_content_file(
                        fichier_pdf, nom_defaut=nom_fichier_pdf
                    )
                    if lu_pdf is not None:
                        cf_pdf, sha_pdf = lu_pdf
                        doc_r, ver_r, liaison_r, _ = _archiver_dans_document(
                            projet=projet,
                            categorie=CategorieDocument.RAPPORTS,
                            content_file=cf_pdf,
                            sha256=sha_pdf,
                            source_type=TypeSourceLiaison.F2_RAPPORT,
                            source_id=rapport.pk,
                            nom_document=nom_synthese,
                            createur=auteur_rapport,
                            description=(
                                f"Rapport journalier approuvé du {rapport.date_rapport:%d/%m/%Y} "
                                f"sur le chantier {projet.reference}."
                            ),
                            commentaire=(
                                f"Rapport journalier approuvé ({rapport.date_rapport:%d/%m/%Y})"
                            ),
                            document_existant=doc_synthese_existant,
                            cle_regroupement_notif=cle_notif,
                        )
                        hashes_rapports.add(sha_pdf)
                        bilan["rapport"] = (doc_r, ver_r, liaison_r)
                elif doc_synthese_existant is not None:
                    # Déjà généré lors d'une exécution précédente : strictement idempotent
                    # (évite le recalcul ReportLab dont les horodatages changent le SHA-256).
                    ver_existante = doc_synthese_existant.derniere_version
                    liaison_existante = next(
                        (
                            liaison
                            for liaison in liaisons_existantes
                            if liaison.document_id == doc_synthese_existant.pk
                        ),
                        None,
                    )
                    bilan["rapport"] = (doc_synthese_existant, ver_existante, liaison_existante)
                else:
                    try:
                        pdf_bytes = generer_pdf_synthese_rapport(rapport, journal)
                    except ImportError:
                        logger.warning(
                            "ReportLab absent : fiche PDF de synthèse non générée pour rapport %s",
                            rapport.pk,
                        )
                        pdf_bytes = None
                    if pdf_bytes:
                        sha_pdf = hashlib.sha256(pdf_bytes).hexdigest()
                        cf_pdf = ContentFile(pdf_bytes, name=nom_fichier_pdf)
                        doc_r, ver_r, liaison_r, _ = _archiver_dans_document(
                            projet=projet,
                            categorie=CategorieDocument.RAPPORTS,
                            content_file=cf_pdf,
                            sha256=sha_pdf,
                            source_type=TypeSourceLiaison.F2_RAPPORT,
                            source_id=rapport.pk,
                            nom_document=nom_synthese,
                            createur=auteur_rapport,
                            description=(
                                f"Fiche de synthèse du rapport journalier approuvé du "
                                f"{rapport.date_rapport:%d/%m/%Y} ({projet.reference})."
                            ),
                            commentaire=(
                                f"Synthèse PDF générée automatiquement — "
                                f"rapport approuvé du {rapport.date_rapport:%d/%m/%Y}"
                            ),
                            document_existant=None,
                            cle_regroupement_notif=cle_notif,
                        )
                        hashes_rapports.add(sha_pdf)
                        bilan["rapport"] = (doc_r, ver_r, liaison_r)
            except Exception:
                logger.exception(
                    "Échec non bloquant de l'archivage PDF du rapport approuvé %s",
                    rapport.pk,
                )

            # 2. Archivage des photos de chantier (JournalChantier.saisie["photos"] -> PHOTOS)
            for idx, photo in enumerate(saisie.get("photos") or [], start=1):
                if not isinstance(photo, dict):
                    continue
                try:
                    decode = _decoder_data_uri(photo.get("fichier"))
                    if decode is None:
                        continue
                    mime, octets = decode
                    mime, octets = _convertir_webp_si_necessaire(mime, octets)
                    ext = _EXTENSIONS_PAR_MIME.get(mime)
                    if not ext:
                        logger.warning(
                            "Format photo %s non accepté par la GED ignoré (rapport=%s)",
                            mime,
                            rapport.pk,
                        )
                        continue
                    if len(octets) > TAILLE_MAX_FICHIER_OCTETS:
                        continue

                    sha256 = hashlib.sha256(octets).hexdigest()
                    if sha256 in hashes_photos:
                        continue

                    cle = str(photo.get("cle") or f"photo_{idx:02d}")
                    legende = str(photo.get("legende") or "").strip()
                    nom_fichier = _normaliser_nom_fichier(
                        f"photo_{rapport.date_rapport:%Y%m%d}_{cle}{ext}",
                        extension_secours=ext,
                    )
                    nom_doc = (
                        f"Photo chantier ({rapport.date_rapport:%d/%m/%Y}) — {legende}"
                        if legende
                        else f"Photo chantier ({rapport.date_rapport:%d/%m/%Y}) — {cle}"
                    )[:255]

                    details_desc = [
                        f"Photo issue du rapport journalier du {rapport.date_rapport:%d/%m/%Y}."
                    ]
                    if photo.get("horodatage_utc"):
                        details_desc.append(f"Prise de vue : {photo['horodatage_utc']}.")
                    if photo.get("latitude") is not None and photo.get("longitude") is not None:
                        details_desc.append(
                            f"GPS : {photo['latitude']}, {photo['longitude']}."
                        )

                    cf_photo = ContentFile(octets, name=nom_fichier)
                    doc_p, ver_p, liaison_p, _ = _archiver_dans_document(
                        projet=projet,
                        categorie=CategorieDocument.PHOTOS,
                        content_file=cf_photo,
                        sha256=sha256,
                        source_type=TypeSourceLiaison.F2_RAPPORT,
                        source_id=rapport.pk,
                        nom_document=nom_doc,
                        createur=rapport.auteur,
                        description=" ".join(details_desc),
                        commentaire=legende or f"Photo rapport du {rapport.date_rapport:%d/%m/%Y}",
                        document_existant=None,
                        cle_regroupement_notif=cle_notif,
                    )
                    hashes_photos.add(sha256)
                    bilan["photos"].append((doc_p, ver_p, liaison_p))
                except Exception:
                    logger.exception(
                        "Échec non bloquant archivage photo #%d du rapport %s",
                        idx,
                        rapport.pk,
                    )

            # 3. Archivage des pièces jointes (JournalChantier.saisie["pieces_jointes"])
            for idx, pj in enumerate(saisie.get("pieces_jointes") or [], start=1):
                if not isinstance(pj, dict):
                    continue
                try:
                    decode = _decoder_data_uri(pj.get("fichier"))
                    if decode is None:
                        continue
                    mime, octets = decode
                    mime, octets = _convertir_webp_si_necessaire(mime, octets)
                    ext = _EXTENSIONS_PAR_MIME.get(mime)
                    if not ext:
                        logger.warning(
                            "Pièce jointe au format %s hors périmètre GED ignorée (rapport=%s)",
                            mime,
                            rapport.pk,
                        )
                        continue
                    if len(octets) > TAILLE_MAX_FICHIER_OCTETS:
                        continue

                    sha256 = hashlib.sha256(octets).hexdigest()
                    est_image = mime in ("image/jpeg", "image/png")
                    categorie_cible = (
                        CategorieDocument.PHOTOS if est_image else CategorieDocument.RAPPORTS
                    )
                    hashes_cibles = hashes_photos if est_image else hashes_rapports
                    if sha256 in hashes_cibles:
                        continue

                    nom_pj = str(
                        pj.get("nom") or pj.get("cle") or f"piece_jointe_{idx:02d}"
                    ).strip()
                    nom_fichier = _normaliser_nom_fichier(nom_pj, extension_secours=ext)
                    nom_doc = (
                        f"Pièce jointe ({rapport.date_rapport:%d/%m/%Y}) — {Path(nom_fichier).stem}"
                    )[:255]

                    cf_pj = ContentFile(octets, name=nom_fichier)
                    doc_pj, ver_pj, liaison_pj, _ = _archiver_dans_document(
                        projet=projet,
                        categorie=categorie_cible,
                        content_file=cf_pj,
                        sha256=sha256,
                        source_type=TypeSourceLiaison.F2_RAPPORT,
                        source_id=rapport.pk,
                        nom_document=nom_doc,
                        createur=rapport.auteur,
                        description=(
                            f"Pièce jointe « {nom_pj} » du rapport journalier approuvé "
                            f"du {rapport.date_rapport:%d/%m/%Y}."
                        ),
                        commentaire=f"Pièce jointe rapport du {rapport.date_rapport:%d/%m/%Y}",
                        document_existant=None,
                        cle_regroupement_notif=cle_notif,
                    )
                    hashes_cibles.add(sha256)
                    bilan["pieces_jointes"].append((doc_pj, ver_pj, liaison_pj))
                except Exception:
                    logger.exception(
                        "Échec non bloquant archivage pièce jointe #%d du rapport %s",
                        idx,
                        rapport.pk,
                    )
    except Exception:
        logger.exception(
            "Échec non bloquant de l'archivage GED pour RapportJournalier %s",
            getattr(rapport, "pk", None),
        )

    return bilan


def archiver_rapport_approuve_par_id(rapport_id: Any, entreprise_id: Any) -> None:
    """Point d'entrée différé (`on_commit`) pour archiver un `RapportJournalier` approuvé."""
    if not rapport_id or not entreprise_id:
        return
    try:
        with _contexte_pour_entreprise(entreprise_id):
            rapport = (
                RapportJournalier.objects.select_related(
                    "projet",
                    "projet__entreprise",
                    "auteur",
                    "valide_par",
                )
                .filter(
                    pk=rapport_id,
                    statut=StatutRapport.APPROUVE,
                    supprime_le__isnull=True,
                )
                .first()
            )
            if rapport is not None:
                archiver_rapport_approuve(rapport)
    except Exception:
        logger.exception(
            "Échec non bloquant dans archiver_rapport_approuve_par_id (rapport=%s)",
            rapport_id,
        )
