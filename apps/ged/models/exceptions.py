"""Exceptions métier propres à l'application GED — CCD Digital.

Module CDC : 11 (Gestion Documentaire)
Synthèse F6 validée par le Product Owner (12/11/2026).
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import status

from apps.core.exceptions import ErreurMetier


class DocumentAutomatiqueNonSupprimable(ErreurMetier):
    """Un document remonté automatiquement (F1, F2 ou F9) ne peut pas être supprimé.

    Règle d'intégrité absolue (F6 §5) : même l'Administrateur ne peut pas le supprimer.
    delete() et suppression logique lèvent cette exception.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code_metier = "document_automatique_non_supprimable"
    default_detail = _(
        "Ce document a été généré automatiquement par un module métier (F1, F2 ou F9) "
        "et ne peut pas être supprimé."
    )


class SuppressionVersionInterdite(ErreurMetier):
    """Toutes les versions d'un document sont conservées (sans perte).

    Règle de traçabilité juridique F6 §2 & §8 : l'historique complet v1 -> v2... est conservé.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code_metier = "suppression_version_interdite"
    default_detail = _(
        "Les versions d'un document sont conservées sans perte pour traçabilité juridique "
        "et ne peuvent pas être supprimées individuellement."
    )


class TailleFichierDepassee(ErreurMetier):
    """La taille du fichier dépasse le plafond de 50 Mo (F6 §2)."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code_metier = "taille_fichier_depassee"
    default_detail = _(
        "La taille du fichier dépasse la limite maximale autorisée de 50 Mo."
    )


class FormatFichierNonAutorise(ErreurMetier):
    """Format de fichier non supporté dans le périmètre MVP F6."""

    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "format_fichier_non_autorise"
    default_detail = _(
        "Le format de fichier n'est pas autorisé. "
        "Formats autorisés dans le périmètre F6 : PDF, JPG, PNG, DOCX, XLSX."
    )
