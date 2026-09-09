"""Application « finance »

Budgets, bons de paiement, signatures, soldes intervenants, rejets de travaux.

Schéma       : tenant
Module CDC   : 3
Entités MCD  : Budget, Depense, BonPaiement, LigneBonPaiement, SignatureBon, ParametreDelegation,
               SoldeIntervenant, Avance, RejetTravaux, SituationTravaux
"""

# Les modèles concrets sont définis dans des fichiers séparés puis
# réexportés ici. Voir 04_Conception/architecture_base_donnees/MLD_CCD_Digital.md

from .bon_paiement import BonPaiement, SignatureBon

__all__ = ["BonPaiement", "SignatureBon"]
