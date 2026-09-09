"""Application « tiers »

Référentiel unique des acteurs externes (décision H3 du MCD).

Schéma       : tenant
Module CDC   : 4 · 9 · 10
Entités MCD  : Tiers, RoleTiers, ContactTiers
"""

from .tiers import RoleTiers, Tiers

__all__ = ["RoleTiers", "Tiers"]
