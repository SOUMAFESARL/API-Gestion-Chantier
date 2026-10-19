"""Statistiques calculées sur les activités actives, sans dépenses fictives."""

from decimal import Decimal

from django.utils import timezone

from apps.core.enums import StatutActivite
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_activite,
    ponderer_lots_par_budget,
)


def pourcentage_realise(activite):
    """Calcule le pourcentage de réalisation d'une activité sous forme de Decimal."""
    return Decimal(str(calculer_avancement_physique_activite(activite)))


def statistiques_lots(lots):
    """Calcule les statistiques consolidées d'une collection de lots actifs.

    Unifié avec le moteur d'indice de santé et la SFD F3 (§4.3, RG-F3-05) :
    - Moyenne pondérée par budget initial des lots via ponderer_lots_par_budget.
    - Les lots sans budget sont exclus du calcul.
    - Pondération toujours 'BUDGET'.
    """
    lots_actifs = [
        lot for lot in lots
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]
    activites = [
        a for lot in lots_actifs for a in lot.activites.all()
        if getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None
    ]

    avancement = ponderer_lots_par_budget(lots_actifs)
    ponderation = "BUDGET"

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
    }

