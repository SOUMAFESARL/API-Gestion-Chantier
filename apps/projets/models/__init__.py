"""Application « projets »

Projets, lots, activités, affectations, bordereaux de prix, indice de santé.

Schéma       : tenant
Module CDC   : 1
Entités MCD  : Projet, Lot, Activite, AffectationProjet, BordereauPrix, LigneBordereau,
               HistoriqueDate, SanteHistorique
"""

from .activite import Activite
from .arret_chantier import ArretChantier
from .contrat import ProjetContrat
from .equipe import AffectationEquipeActivite, EquipeChantier, MembreEquipeChantier
from .historique_date import HistoriqueDate, TypeObjetHistorique
from .lot import Lot
from .motif_report import MotifReport
from .override import ProjetRoleModuleOverride
from .projet import AffectationProjet, Projet
from .sante_snapshot import SanteProjetSnapshot

__all__ = [
    "Activite",
    "AffectationEquipeActivite",
    "AffectationProjet",
    "ArretChantier",
    "EquipeChantier",
    "HistoriqueDate",
    "Lot",
    "MembreEquipeChantier",
    "MotifReport",
    "Projet",
    "ProjetContrat",
    "ProjetRoleModuleOverride",
    "SanteProjetSnapshot",
    "TypeObjetHistorique",
]
