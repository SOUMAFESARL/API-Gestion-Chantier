"""Modèles du catalogue souverain CCD Digital."""

from .decoupage import (
    LigneModelePlateforme,
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    NiveauModelePlateforme,
    ValeurListePlateforme,
)
from .entreprise_module import EntrepriseModule
from .modele_role import ModeleRole, ModeleRoleModule
from .module import CatalogueModule
from .permission import CataloguePermission
from .referentiel import CategorieReferentiel, ReferentielPlateforme

# Alias pour compatibilité sémantique
Module = CatalogueModule
Permission = CataloguePermission

__all__ = [
    "CatalogueModule",
    "CataloguePermission",
    "LigneModelePlateforme",
    "ListeValeursPlateforme",
    "ModeleDecoupagePlateforme",
    "NiveauModelePlateforme",
    "ValeurListePlateforme",
    "EntrepriseModule",
    "ModeleRole",
    "ModeleRoleModule",
    "Module",
    "Permission",
    "CategorieReferentiel",
    "ReferentielPlateforme",
]
