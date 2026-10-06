"""Permissions DRF propres au module « chantier » — rapports journaliers.

Contrôle d'accès à deux niveaux (Socle Commun §2.3) :
- Niveau 1 : Rôle global et permissions du module (CHANTIER).
- Niveau 2 : Affectation au projet spécifique.
"""

from rest_framework import permissions

from apps.core.permissions import GardePermissionProjet

__all__ = [
    "PeutConsulterRapports",
    "PeutRedigerRapports",
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
