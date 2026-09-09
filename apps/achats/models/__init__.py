"""Application « achats »

Achats et approvisionnements. NIVEAU A — entités identifiées, MLD à produire.

Schéma       : tenant
Module CDC   : 4
Entités MCD  : DemandeAchat, LigneDemande, ValidationAchat, Consultation, OffreFournisseur,
               BonCommande, LigneCommande, Reception, LigneReception, EvaluationFournisseur
"""

# Les modèles concrets sont définis dans des fichiers séparés puis
# réexportés ici. Voir 04_Conception/architecture_base_donnees/MLD_CCD_Digital.md

from .reception import ReceptionMateriau

__all__ = ["ReceptionMateriau"]
