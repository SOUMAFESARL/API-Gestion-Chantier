"""Indicateurs de présentation sans modification de l'avancement stocké."""

from decimal import Decimal

from apps.core.enums import StatutProjet


def avancement_restant(projet):
    if projet.statut == StatutProjet.TERMINE:
        return 0.0
    total = Decimal(0)
    poids_total = Decimal(0)
    for lot in projet.lots.all():
        if not lot.est_actif or lot.supprime_le is not None:
            continue
        for activite in lot.activites.all():
            if not activite.est_actif or activite.supprime_le is not None:
                continue
            poids = activite.poids if activite.poids is not None else Decimal(1)
            if poids <= 0 or activite.quantite_prevue <= 0:
                continue
            realise = min(Decimal(100), max(
                Decimal(0), activite.quantite_realisee / activite.quantite_prevue * 100
            ))
            total += realise * poids
            poids_total += poids
    realise = total / poids_total if poids_total else Decimal(projet.avancement_reel or 0)
    return float(round(max(Decimal(0), min(Decimal(100), 100 - realise)), 2))
