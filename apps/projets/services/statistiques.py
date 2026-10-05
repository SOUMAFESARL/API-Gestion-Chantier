"""Statistiques calculées sur les activités actives, sans dépenses fictives."""

from decimal import Decimal

from django.utils import timezone

from apps.core.enums import StatutActivite
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_activite,
    calculer_avancement_physique_lot,
)


def pourcentage_realise(activite):
    """Calcule le pourcentage de réalisation d'une activité sous forme de Decimal."""
    return Decimal(str(calculer_avancement_physique_activite(activite)))


def statistiques_lots(lots):
    """Calcule les statistiques consolidées d'une collection de lots actifs.

    Unifié avec le moteur d'indice de santé (C3) :
    - Pour 1 lot : délégation directe à calculer_avancement_physique_lot(lot).
    - Pour plusieurs lots : moyenne pondérée par budget initial des lots (repli uniforme si incomplet).
    """
    lots_actifs = [
        lot for lot in lots
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]
    activites = [
        a for lot in lots_actifs for a in lot.activites.all()
        if getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None
    ]

    # Seuls les lots ayant une consistance (budget propre ou au moins une activité active) participent au calcul d'avancement
    lots_pertinents = [
        lot for lot in lots_actifs
        if (getattr(lot, "budget_initial_montant", None) is not None and lot.budget_initial_montant > 0)
        or any(getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None for a in lot.activites.all())
    ]

    if not lots_pertinents:
        avancement = 0.0
        ponderation = "UNIFORME"
    elif len(lots_pertinents) == 1:
        lot_unique = lots_pertinents[0]
        avancement = calculer_avancement_physique_lot(lot_unique)
        activites_lot = [
            a for a in lot_unique.activites.all()
            if getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None
        ]
        budget_complet = bool(activites_lot) and all(
            a.budget_initial_montant is not None and a.budget_initial_montant > 0
            for a in activites_lot
        )
        ponderation = "BUDGET" if budget_complet else "UNIFORME"
    else:
        # Multiples lots (consolidation niveau projet)
        from apps.projets.services.sante_calculs import obtenir_budget_effectif_lot

        budgets_lots = [obtenir_budget_effectif_lot(lot) for lot in lots_pertinents]
        budget_complet_lots = all(b is not None and b > 0 for b in budgets_lots)
        poids = [b if budget_complet_lots else 1.0 for b in budgets_lots]
        total_poids = sum(poids)
        if total_poids <= 0:
            avancement = 0.0
        else:
            avancements_lots = [calculer_avancement_physique_lot(l) for l in lots_pertinents]
            somme = sum(av * p for av, p in zip(avancements_lots, poids, strict=True))
            avancement = float(round(somme / total_poids, 2))
        ponderation = "BUDGET" if budget_complet_lots else "UNIFORME"

    aujourd_hui = timezone.localdate()
    return {
        "lots_count": len(lots_actifs),
        "activites_count": len(activites),
        "avancement_pondere": avancement,
        "ponderation": ponderation,
        "activites_en_retard": sum(
            1
            for a in activites
            if getattr(a, "date_fin_prevue", None)
            and isinstance(getattr(a, "date_fin_prevue", None), type(aujourd_hui))
            and a.date_fin_prevue < aujourd_hui
            and float(calculer_avancement_physique_activite(a)) < 100.0
            and getattr(a, "statut", None) != StatutActivite.CLOTURE
        ),
        "budget_activites_montant": sum(a.budget_initial_montant or 0 for a in activites),
    }

