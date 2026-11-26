"""Validation et versionnement du contrat du marché d'un projet.

Un seul contrat actif par projet : téléverser un nouveau contrat archive automatiquement
l'ancien actif (`est_actif=False`) et crée la version suivante (`version=N+1`, `est_actif=True`),
tout en conservant l'historique complet téléchargeable.
"""

import logging
import warnings
from pathlib import Path

from django.utils import timezone
from PIL import Image
from pypdf import PdfReader
from rest_framework import serializers

from apps.core.enums import ActionAudit
from apps.projets.models import ProjetContrat

logger = logging.getLogger(__name__)
MAX_FICHIER = 50 * 1024 * 1024
MAX_LOT = 50 * 1024 * 1024
NOMBRE_MAX_CONTRATS_ACTIFS = 1
FORMATS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jepg": "image/jpeg",
}


def valider_fichier_contrat(fichier):
    extension = Path(fichier.name).suffix.lower()
    if extension not in FORMATS:
        raise serializers.ValidationError("Formats acceptes : PDF, JPG, JPEG, PNG (JEPG accepte).")
    if not fichier.size or fichier.size > MAX_FICHIER:
        raise serializers.ValidationError("Le fichier doit contenir entre 1 octet et 50 Mo.")
    try:
        fichier.seek(0)
        if extension == ".pdf":
            if not fichier.read(5) == b"%PDF-":
                raise ValueError("Signature PDF absente")
            fichier.seek(0)
            reader = PdfReader(fichier)
            if not reader.is_encrypted and not len(reader.pages):
                raise ValueError("PDF sans page")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(fichier)
                expected = "PNG" if extension == ".png" else "JPEG"
                if image.format != expected or image.width * image.height > 30_000_000:
                    raise ValueError("Format image incorrect ou dimensions excessives")
                image.verify()
    except Exception as exc:
        # Malformed PDFs can fail at several parsing stages; never store them.
        raise serializers.ValidationError(
            "Contenu invalide ou incompatible avec l'extension."
        ) from exc
    finally:
        fichier.seek(0)
    return fichier


def ajouter_contrats(projet, fichiers, utilisateur, stockes):
    """Dépose un nouveau contrat du marché en remplaçant l'actif précédent et en conservant
    l'historique des versions (`version` incrémentée, anciens contrats passés à `est_actif=False`).

    L'appelant possède la transaction SQL et nettoie `stockes` en cas d'échec.
    """
    if not fichiers:
        return None
    if len(fichiers) > NOMBRE_MAX_CONTRATS_ACTIFS:
        raise serializers.ValidationError(
            {
                "contrat": (
                    "Un seul contrat du marché peut être déposé à la fois : le nouveau "
                    "remplace le contrat actif tout en conservant l'historique des versions."
                )
            }
        )

    fichier = fichiers[0]
    versions = list(
        ProjetContrat.tous_objets.filter(projet=projet)
        .select_for_update()
        .values_list("version", flat=True)
    )
    derniere_version = max(versions) if versions else 0
    ancien_actif = (
        ProjetContrat.objects.filter(projet=projet, est_actif=True).select_for_update().first()
    )
    if ancien_actif is not None:
        ProjetContrat.objects.filter(projet=projet, est_actif=True).update(
            est_actif=False,
            modifie_le=timezone.now(),
        )

    auteur = (
        utilisateur
        if utilisateur and getattr(utilisateur, "is_authenticated", False)
        else None
    )
    document = ProjetContrat(
        projet=projet,
        nom=fichier.name[:255],
        taille=fichier.size,
        type_contenu=FORMATS[Path(fichier.name).suffix.lower()],
        version=derniere_version + 1,
        est_actif=True,
        cree_par=auteur,
    )
    document.fichier.save(fichier.name, fichier, save=False)
    stockes.append((document.fichier.storage, document.fichier.name))
    document.save()

    from apps.audit.services import journaliser

    journaliser(
        action=ActionAudit.MODIFICATION if ancien_actif else ActionAudit.CREATION,
        type_entite="ProjetContrat",
        entite_id=document.pk,
        utilisateur_id=getattr(utilisateur, "pk", None)
        if utilisateur and getattr(utilisateur, "is_authenticated", False)
        else None,
        valeur_avant=(
            {"id": str(ancien_actif.pk), "nom": ancien_actif.nom, "version": ancien_actif.version}
            if ancien_actif
            else None
        ),
        valeur_apres={
            "projet_id": str(projet.pk),
            "nom": document.nom,
            "version": document.version,
            "est_actif": True,
        },
    )
    return document


def nettoyer_contrats(stockes):
    for stockage, nom in stockes:
        try:
            stockage.delete(nom)
        except Exception:
            logger.exception("Echec de nettoyage d'un contrat apres rollback : %s", nom)
