"""Validateurs de fichiers pour le module GED — CCD Digital (F6).

Spécifications validées F6 :
- Formats autorisés : PDF, JPG, PNG, DOCX, XLSX
- Contrôle strict du type MIME réel (magic bytes / inspection structurelle)
- Taille maximale autorisée : 50 Mo par fichier
- Empreinte cryptographique : SHA-256
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

__all__ = [
    "EXTENSIONS_AUTORISEES",
    "EXTENSION_MIME_MAPPING",
    "MIME_TYPES_AUTORISES",
    "TAILLE_MAX_FICHIER_OCTETS",
    "calculer_sha256",
    "detecter_type_mime",
    "obtenir_taille_fichier",
    "valider_extension_fichier",
    "valider_fichier_ged",
    "valider_taille_fichier",
]

# Taille maximale autorisée : 50 Mo (50 * 1024 * 1024 octets)
TAILLE_MAX_FICHIER_OCTETS: int = 50 * 1024 * 1024

# Extensions autorisées (minuscules, avec point)
EXTENSIONS_AUTORISEES: frozenset[str] = frozenset({
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".docx",
    ".xlsx",
})

# Types MIME autorisés
MIME_PDF = "application/pdf"
MIME_JPEG = "image/jpeg"
MIME_PNG = "image/png"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MIME_TYPES_AUTORISES: frozenset[str] = frozenset({
    MIME_PDF,
    MIME_JPEG,
    MIME_PNG,
    MIME_DOCX,
    MIME_XLSX,
})

# Correspondance extension -> types MIME acceptables
EXTENSION_MIME_MAPPING: dict[str, set[str]] = {
    ".pdf": {MIME_PDF},
    ".jpg": {MIME_JPEG},
    ".jpeg": {MIME_JPEG},
    ".png": {MIME_PNG},
    ".docx": {MIME_DOCX},
    ".xlsx": {MIME_XLSX},
}


def obtenir_taille_fichier(fichier: Any) -> int:
    """Retourne la taille en octets d'un fichier en préservant le curseur."""
    taille = getattr(fichier, "size", None)
    if taille is not None:
        return int(taille)

    if hasattr(fichier, "seek") and hasattr(fichier, "tell"):
        position_actuelle = fichier.tell()
        fichier.seek(0, 2)  # Fin du fichier
        taille = fichier.tell()
        fichier.seek(position_actuelle)
        return int(taille)

    raise ValidationError(
        _("Impossible de déterminer la taille du fichier."),
        code="taille_indeterminee",
    )


def valider_taille_fichier(fichier: Any, max_octets: int = TAILLE_MAX_FICHIER_OCTETS) -> int:
    """Vérifie que le fichier n'est pas vide et ne dépasse pas la limite autorisée (50 Mo)."""
    taille = obtenir_taille_fichier(fichier)
    if taille <= 0:
        raise ValidationError(
            _("Le fichier déposé est vide (0 octet)."),
            code="fichier_vide",
        )
    if taille > max_octets:
        limite_mo = max_octets // (1024 * 1024)
        taille_mo = taille / (1024 * 1024)
        msg = (
            f"La taille du fichier ({taille_mo:.1f} Mo) dépasse "
            f"la limite maximale autorisée de {limite_mo} Mo."
        )
        raise ValidationError(_(msg), code="taille_fichier_trop_grande")
    return taille


def valider_extension_fichier(nom_fichier: str) -> str:
    """Valide l'extension du nom de fichier et renvoie l'extension normalisée."""
    if not nom_fichier or "." not in nom_fichier:
        raise ValidationError(
            _("Le nom de fichier doit comporter une extension valide."),
            code="extension_manquante",
        )
    ext = Path(nom_fichier).suffix.lower()
    if ext not in EXTENSIONS_AUTORISEES:
        raise ValidationError(
            _(
                "Extension non autorisée. Les formats autorisés sont : "
                "PDF, JPG, PNG, DOCX, XLSX."
            ),
            code="extension_non_autorisee",
        )
    return ext


def detecter_type_mime(fichier: Any) -> str:
    """Détecte le type MIME réel à partir des magic bytes et de la structure du fichier.

    Inspecte le contenu binaire réel sans se fier uniquement à l'extension.
    """
    if hasattr(fichier, "seek"):
        fichier.seek(0)

    # Lecture des premiers 2048 octets pour identifier la signature
    header = fichier.read(2048) if hasattr(fichier, "read") else b""

    if hasattr(fichier, "seek"):
        fichier.seek(0)

    if not header:
        raise ValidationError(
            _("Impossible d'inspecter le contenu : le fichier est vide."),
            code="fichier_vide",
        )

    # 1. Signature PDF (%PDF-)
    if header.startswith(b"%PDF-"):
        return MIME_PDF

    # 2. Signature JPEG (\xff\xd8\xff)
    if header.startswith(b"\xff\xd8\xff"):
        return MIME_JPEG

    # 3. Signature PNG (\x89PNG\r\n\x1a\n)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return MIME_PNG

    # 4. Formats OpenXML (DOCX, XLSX) basés sur conteneur ZIP (PK\x03\x04)
    if header.startswith(b"PK\x03\x04"):
        try:
            if hasattr(fichier, "seek"):
                fichier.seek(0)
            with zipfile.ZipFile(fichier, "r") as zf:
                fichiers_contenus = set(zf.namelist())
                # DOCX contient word/document.xml ou le sous-dossier word/
                if any(nom.startswith("word/") for nom in fichiers_contenus):
                    return MIME_DOCX
                # XLSX contient xl/workbook.xml ou le sous-dossier xl/
                if any(nom.startswith("xl/") for nom in fichiers_contenus):
                    return MIME_XLSX
        except (zipfile.BadZipFile, Exception):
            pass
        finally:
            if hasattr(fichier, "seek"):
                fichier.seek(0)

    raise ValidationError(
        _(
            "Contenu de fichier non reconnu ou non autorisé. "
            "Formats valides acceptés : PDF, JPG, PNG, DOCX, XLSX."
        ),
        code="type_mime_invalide",
    )


def calculer_sha256(fichier: Any) -> str:
    """Calcule le hash SHA-256 hexadécimal du fichier et réinitialise le pointeur à 0."""
    hasher = hashlib.sha256()

    if hasattr(fichier, "seek"):
        fichier.seek(0)

    if hasattr(fichier, "chunks") and callable(fichier.chunks):
        for chunk in fichier.chunks():
            hasher.update(chunk)
    elif hasattr(fichier, "read"):
        while True:
            chunk = fichier.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    else:
        raise ValidationError(
            _("Impossible de lire le fichier pour calculer son empreinte."),
            code="lecture_impossible",
        )

    if hasattr(fichier, "seek"):
        fichier.seek(0)

    return hasher.hexdigest()


def valider_fichier_ged(fichier: Any, nom_fichier: str | None = None) -> dict[str, Any]:
    """Validation complète d'un fichier GED.

    Vérifie :
    1. Taille du fichier (0 < taille <= 50 Mo)
    2. Extension du nom de fichier (.pdf, .jpg, .jpeg, .png, .docx, .xlsx)
    3. Type MIME réel via magic bytes
    4. Concordance stricte entre l'extension déclarée et le contenu MIME réel
    5. Calcul du hash SHA-256

    Retourne un dictionnaire contenant les métadonnées vérifiées :
    - taille : int
    - extension : str
    - type_mime : str
    - sha256 : str
    - nom : str
    """
    # Détermination du nom de fichier pour extraire l'extension
    nom_fichier_physique = getattr(fichier, "name", "")
    nom_a_tester = ""
    if nom_fichier_physique and "." in nom_fichier_physique:
        nom_a_tester = nom_fichier_physique
    elif nom_fichier and "." in nom_fichier:
        nom_a_tester = nom_fichier
    else:
        nom_a_tester = nom_fichier_physique or nom_fichier or ""

    if not nom_a_tester or "." not in nom_a_tester:
        raise ValidationError(
            _("Le fichier physique doit comporter un nom avec une extension valide."),
            code="nom_fichier_manquant",
        )

    # 1. Vérification de l'extension
    extension = valider_extension_fichier(nom_a_tester)

    # 2. Vérification de la taille
    taille = valider_taille_fichier(fichier, TAILLE_MAX_FICHIER_OCTETS)

    # 3. Détection et validation du type MIME réel
    type_mime = detecter_type_mime(fichier)

    # 4. Cohérence extension vs MIME réel
    mimes_attendus = EXTENSION_MIME_MAPPING.get(extension, set())
    if type_mime not in mimes_attendus:
        raise ValidationError(
            _(
                f"Incohérence détectée : le contenu réel du fichier ({type_mime}) "
                f"ne correspond pas à son extension déclarée ({extension})."
            ),
            code="incoherence_extension_mime",
        )

    # 5. Calcul de l'empreinte SHA-256
    hash_sha256 = calculer_sha256(fichier)

    return {
        "taille": taille,
        "extension": extension,
        "type_mime": type_mime,
        "sha256": hash_sha256,
        "nom": nom_a_tester,
    }
