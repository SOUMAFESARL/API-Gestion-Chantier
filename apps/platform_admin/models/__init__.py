"""Application « platform_admin »

Super Admin CCD Digital : métriques plateforme, impersonification.

Schéma       : public
Module CDC   : —
Entités MCD  : JournalPlateforme, IdentitePlateforme
"""

from .identite import IdentitePlateforme
from .journal import JournalPlateforme

__all__ = ["IdentitePlateforme", "JournalPlateforme"]
