"""Selectors du module « platform_admin »."""

from .clients import formater_client_plateforme, lister_clients_plateforme, obtenir_fiche_client
from .indicateurs import (
    obtenir_evolution_abonnements,
    obtenir_indicateurs_plateforme,
    obtenir_tendances_indicateurs,
)

__all__ = [
    "formater_client_plateforme",
    "lister_clients_plateforme",
    "obtenir_evolution_abonnements",
    "obtenir_fiche_client",
    "obtenir_indicateurs_plateforme",
    "obtenir_tendances_indicateurs",
]
