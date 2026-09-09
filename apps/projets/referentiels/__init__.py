"""Référentiels du module projets."""

from .villes import (
    AGGLOMERATION_PRINCIPALE,
    LOCALITES,
    lister_villes,
    nom_agglomeration,
    pays_couvert,
    resoudre_coordonnees,
)

__all__ = [
    "AGGLOMERATION_PRINCIPALE",
    "LOCALITES",
    "lister_villes",
    "nom_agglomeration",
    "pays_couvert",
    "resoudre_coordonnees",
]
