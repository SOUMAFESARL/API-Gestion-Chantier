"""Selectors du module « platform_admin »."""

from .clients import formater_client_plateforme, lister_clients_plateforme, obtenir_fiche_client
from .indicateurs import (
    obtenir_evolution_abonnements,
    obtenir_indicateurs_plateforme,
    obtenir_tendances_indicateurs,
)
from .journal import codes_actions_journal, journal_plateforme

__all__ = [
    "codes_actions_journal",
    "formater_client_plateforme",
    "journal_plateforme",
    "lister_clients_plateforme",
    "obtenir_evolution_abonnements",
    "obtenir_fiche_client",
    "obtenir_indicateurs_plateforme",
    "obtenir_tendances_indicateurs",
]
