"""Statistiques calculées sur les activités actives, sans dépenses fictives."""

from decimal import Decimal

from django.utils import timezone

from apps.core.enums import StatutActivite


def pourcentage_realise(activite):
    if activite.statut == StatutActivite.CLOTURE:
        return Decimal(100)
    if activite.quantite_prevue <= 0:
        return Decimal(0)
    return max(
        Decimal(0), min(Decimal(100), activite.quantite_realisee / activite.quantite_prevue * 100)
    )


def statistiques_lots(lots):
    lots = [lot for lot in lots if lot.est_actif and lot.supprime_le is None]
    activites = [
        a for lot in lots for a in lot.activites.all() if a.est_actif and a.supprime_le is None
    ]
    budget_complet = bool(activites) and all(
        a.budget_initial_montant is not None and a.budget_initial_montant > 0 for a in activites
    )
    poids = [Decimal(a.budget_initial_montant) if budget_complet else Decimal(1) for a in activites]
    somme = sum(poids, Decimal(0))
    total = sum(
        (pourcentage_realise(a) * p for a, p in zip(activites, poids, strict=True)), Decimal(0)
    )
    aujourd_hui = timezone.localdate()
    return {
        "lots_count": len(lots),
        "activites_count": len(activites),
        "avancement_pondere": float(round(total / somme, 2)) if somme else 0.0,
        "ponderation": "BUDGET" if budget_complet else "UNIFORME",
        "activites_en_retard": sum(
            1
            for a in activites
            if a.date_fin_prevue
            and a.date_fin_prevue < aujourd_hui
            and pourcentage_realise(a) < 100
            and a.statut != StatutActivite.CLOTURE
        ),
        "budget_activites_montant": sum(a.budget_initial_montant or 0 for a in activites),
    }
