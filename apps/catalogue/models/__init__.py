"""Modèles du catalogue souverain CCD Digital."""

from .entreprise_module import EntrepriseModule
from .modele_role import ModeleRole, ModeleRoleModule
from .module import CatalogueModule
from .permission import CataloguePermission

# Alias pour compatibilité sémantique
Module = CatalogueModule
Permission = CataloguePermission

__all__ = [
    "CatalogueModule",
    "CataloguePermission",
    "EntrepriseModule",
    "ModeleRole",
    "ModeleRoleModule",
    "Module",
    "Permission",
]
