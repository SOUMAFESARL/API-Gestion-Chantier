"""Application « chantier »

Journal de chantier : rapports journaliers, production, photos, blocages.

Schéma       : tenant
Module CDC   : 2
Entités MCD  : RapportJournalier, LigneAvancement, ProductionIntervenant, Photo, Blocage
"""

# Les modèles concrets sont définis dans des fichiers séparés puis
# réexportés ici. Voir 04_Conception/architecture_base_donnees/MLD_CCD_Digital.md

from .rapport_journalier import RapportJournalier

__all__ = ["RapportJournalier"]
