"""Views du module « chantier ».

Journal de chantier : rapports journaliers, production, photos, blocages.
"""

from .blocage import (
    BlocageDetailView,
    BlocagePrendreEnChargeView,
    BlocageResoudreView,
    ProjetBlocageListCreateView,
)
from .rapport_journalier import (
    RapportDetailView,
    RapportListCreateView,
    RapportRejeterView,
    RapportSoumettreView,
    RapportValiderView,
)

__all__ = [
    "BlocageDetailView",
    "BlocagePrendreEnChargeView",
    "BlocageResoudreView",
    "ProjetBlocageListCreateView",
    "RapportDetailView",
    "RapportListCreateView",
    "RapportRejeterView",
    "RapportSoumettreView",
    "RapportValiderView",
]
