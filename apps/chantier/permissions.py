"""Permissions DRF propres au module « chantier » — rapports journaliers.

Contrôle d'accès à deux niveaux (Socle Commun §2.3) :
- Niveau 1 : Rôle global et permissions du module (CHANTIER).
- Niveau 2 : Affectation au projet spécifique.
"""

from rest_framework import permissions

from apps.core.permissions import GardePermissionProjet

__all__ = [
    "PeutApprouverRapports",
    "PeutApprouverSynthese",
    "PeutConsulterRapports",
    "PeutRedigerRapports",
    "PeutRedigerSynthese",
    "PeutValiderRapports",
]


class PeutConsulterRapports(GardePermissionProjet):
    """Vérifie que l'utilisateur peut consulter les rapports de chantier (Règle D-08)."""

    code_permission = "chantier.lire"


class PeutRedigerRapports(GardePermissionProjet):
    """Vérifie que l'utilisateur peut créer ou modifier un rapport journalier (Règle D-08)."""

    code_permission = "chantier.rediger"


class PeutValiderRapports(GardePermissionProjet):
    """Vérifie que l'utilisateur a autorité pour valider ou rejeter un rapport (Règle D-08)."""

    code_permission = "chantier.valider"


class PeutApprouverRapports(GardePermissionProjet):
    """Approuver un rapport : l'étape après la validation (30/10/2026)."""

    code_permission = "chantier.approuver"


class PeutRedigerSynthese(GardePermissionProjet):
    """Rédiger et signer la synthèse de la semaine (30/10/2026)."""

    code_permission = "chantier.synthese_rediger"


class PeutApprouverSynthese(GardePermissionProjet):
    """Approuver ou rejeter la synthèse de la semaine (30/10/2026)."""

    code_permission = "chantier.synthese_approuver"
