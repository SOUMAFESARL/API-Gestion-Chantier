"""Application « projets »

Projets, lots, activités, affectations, bordereaux de prix, indice de santé.

Schéma       : tenant
Module CDC   : 1
Entités MCD  : Projet, Lot, Activite, AffectationProjet, BordereauPrix, LigneBordereau,
               HistoriqueDate, SanteHistorique
"""

from .lot import Lot
from .override import ProjetRoleModuleOverride
from .projet import AffectationProjet, Projet

__all__ = ["AffectationProjet", "Lot", "Projet", "ProjetRoleModuleOverride"]
