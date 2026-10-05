"""Services métier pour la gestion des activités de lot (MLD §6.3).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from decimal import Decimal
from typing import Any
from django.db import transaction

from apps.accounts.models import Utilisateur
from apps.projets.models import Activite
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

__all__ = [
    "mettre_a_jour_quantite_realisee",
    "modifier_activite",
]


@transaction.atomic
def modifier_activite(
    *,
    activite: Activite,
    utilisateur: Utilisateur | None = None,
    **champs: Any,
) -> Activite:
    """Modifie les informations d'une activité et déclenche le recalcul de santé (F1)."""
    champs_autorises = {
        "libelle",
        "statut",
        "quantite_prevue",
        "quantite_realisee",
        "budget_initial_montant",
        "poids",
        "ordre",
        "est_actif",
        "unite",
    }
    impact_sante = False
    champs_maj = ["modifie_le"]

    for nom, valeur in champs.items():
        if nom in champs_autorises:
            if getattr(activite, nom) != valeur:
                if nom in {
                    "quantite_realisee",
                    "quantite_prevue",
                    "statut",
                    "budget_initial_montant",
                    "est_actif",
                }:
                    impact_sante = True
                setattr(activite, nom, valeur)
                champs_maj.append(nom)

    activite.save(update_fields=champs_maj)

    if impact_sante and activite.lot and activite.lot.projet_id:
        declencher_recalcul_sante(
            projet_id=activite.lot.projet_id,
            declencheur_type="ACTIVITE_MODIFICATION",
            declencheur_id=str(activite.id),
        )

    return activite


@transaction.atomic
def mettre_a_jour_quantite_realisee(
    *,
    activite: Activite,
    quantite_realisee: Decimal | float | int,
    utilisateur: Utilisateur | None = None,
) -> Activite:
    """Met à jour spécifiquement la quantité réalisée d'une activité."""
    return modifier_activite(
        activite=activite,
        utilisateur=utilisateur,
        quantite_realisee=Decimal(str(quantite_realisee)),
    )
