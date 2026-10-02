"""Validate entire batches before persisting private contract documents."""

import logging
import warnings
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from rest_framework import serializers

from apps.projets.models import ProjetContrat

logger = logging.getLogger(__name__)
MAX_FICHIER = 10 * 1024 * 1024
MAX_LOT = 50 * 1024 * 1024
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
        raise serializers.ValidationError("Le fichier doit contenir entre 1 octet et 10 Mo.")
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
    """The caller owns the SQL transaction and compensates storage on failure."""
    for fichier in fichiers:
        document = ProjetContrat(
            projet=projet,
            nom=fichier.name,
            taille=fichier.size,
            type_contenu=FORMATS[Path(fichier.name).suffix.lower()],
            cree_par=utilisateur,
        )
        document.fichier.save(fichier.name, fichier, save=False)
        stockes.append((document.fichier.storage, document.fichier.name))
        document.save()


def nettoyer_contrats(stockes):
    for stockage, nom in stockes:
        try:
            stockage.delete(nom)
        except Exception:
            logger.exception("Echec de nettoyage d'un contrat apres rollback : %s", nom)
