"""Moteur de calcul pur pour les avancements et le calendrier d'entreprise.

Fonctions pures, déterministes et testables unitairement :
- Formule 1 : Avancement physique activité (quantite_realisee / quantite_prevue).
- Formule 2 : Avancement physique lot (moyenne des activités pondérée par quantite_prevue).
- Formule 3 : Avancement physique projet (moyenne des lots pondérée par budget_initial_montant).
- Formule 4 : Avancement temporel lot et projet (jours ouvrés écoulés vs baseline contractuelle v0).
- Formule 5 : Delta de retard lot et projet (avancement temporel - avancement physique).
- Calendrier d'entreprise et comptage des jours ouvrés.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django_tenants.utils import get_public_schema_name, schema_context

from apps.core.enums import BadgeSante, StatutActivite
from apps.projets.services.calendrier_ouvre import (
    CALENDRIER_PAR_DEFAUT_SEMAINE,
    Calendrier,
    calendrier_entreprise,
)
from apps.referentiels.models import JourFerie

logger = logging.getLogger(__name__)

__all__ = [
    "CALENDRIER_PAR_DEFAUT_SEMAINE",
    "Calendrier",
    "calculer_avancement_physique_activite",
    "calculer_avancement_physique_lot",
    "calculer_avancement_physique_projet",
    "calculer_avancement_temporel_lot",
    "calculer_avancement_temporel_projet",
    "calculer_delta_lot",
    "calculer_delta_projet",
    "calendrier_entreprise",
    "compter_jours_ouvres",
    "couverture_budget_projet",
    "determiner_badge",
    "determiner_badge_brut",
    "est_jour_ouvre",
    "obtenir_jours_feries_ci",
    "ponderer_lots_par_budget",
]


# --------------------------------------------------------------------------
# Calendrier & Jours Ouvrés
# --------------------------------------------------------------------------

def obtenir_jours_feries_ci(annee_min: int, annee_max: int) -> tuple[set[date], bool]:
    """Récupère l'ensemble des jours fériés pour la Côte d'Ivoire (CI) dans le schéma public.

    Retourne (jours_feries_set, est_incomplet).
    est_incomplet vaut True si au moins une année de l'intervalle est totalement absente.
    """
    annees_demandees = set(range(annee_min, annee_max + 1))
    with schema_context(get_public_schema_name()):
        qs = JourFerie.objects.filter(
            pays="CI",
            date_ferie__year__gte=annee_min,
            date_ferie__year__lte=annee_max,
        )
        annees_presentes = set(qs.values_list("date_ferie__year", flat=True).distinct())
        feries = set(qs.values_list("date_ferie", flat=True))

    est_incomplet = not annees_demandees.issubset(annees_presentes)
    return feries, est_incomplet


def est_jour_ouvre(d: date, jours_feries: Calendrier | set[date] | frozenset[date]) -> bool:
    """Vérifie si un jour donné est ouvré.

    Accepte soit une instance de Calendrier d'entreprise (règle des 3 couches :
    exceptions, puis fériés nationaux, puis semaine type), soit un ensemble de dates
    (comportement historique : lundi à vendredi hors dates de l'ensemble).
    """
    if isinstance(jours_feries, Calendrier):
        return jours_feries.est_ouvre(d)
    return d.weekday() < 5 and d not in jours_feries


def compter_jours_ouvres(
    debut: date,
    fin: date,
    jours_feries: Calendrier | set[date] | frozenset[date],
) -> int:
    """Compte le nombre de jours ouvrés inclus entre debut et fin (bornes incluses).

    Accepte soit un Calendrier d'entreprise, soit un ensemble de dates de jours fériés.
    """
    if fin < debut:
        return 0
    total = 0
    courant = debut
    un_jour = timedelta(days=1)
    while courant <= fin:
        if est_jour_ouvre(courant, jours_feries):
            total += 1
        courant += un_jour
    return total


# --------------------------------------------------------------------------
# Avancements Physiques & Temporels
# --------------------------------------------------------------------------

def calculer_avancement_physique_activite(activite) -> float:
    """Calcule l'avancement physique d'une activité (0 à 100 %).

    Règle CDC / SFD F3 §4.1 : Activite.quantite_realisee / Activite.quantite_prevue * 100.
    100 % si clôturée. Plafonné à 100 %, plancher à 0 %.
    0.0 si quantite_prevue <= 0.
    Note : quantite_realisee est désormais alimentée par les rapports approuvés
    (tâche P3) et par les mises à jour manuelles.
    """
    if getattr(activite, "statut", None) == StatutActivite.CLOTURE:
        return 100.0
    q_prevue = getattr(activite, "quantite_prevue", None) or 0
    if q_prevue <= 0:
        return 0.0
    q_realisee = getattr(activite, "quantite_realisee", None) or 0
    pourcentage = (float(q_realisee) / float(q_prevue)) * 100.0
    return float(round(max(0.0, min(100.0, pourcentage)), 2))


def calculer_avancement_physique_lot(lot) -> float:
    """Calcule l'avancement physique d'un lot (SFD F3 §4.2).

    Moyenne des activités actives non supprimées, pondérée par leur quantite_prevue.
    Les activités dont quantite_prevue <= 0 n'entrent pas dans le calcul.
    Si le lot n'a aucune activité active, garde le comportement actuel
    (rendre float(lot.avancement or 0)).
    Si toutes ses activités ont une quantité prévue nulle, rend 0.0.
    """
    activites = [
        a for a in lot.activites.all()
        if getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None
    ]
    if not activites:
        return float(getattr(lot, "avancement", None) or 0.0)

    activites_valides = [
        a for a in activites
        if (getattr(a, "quantite_prevue", None) or 0) > 0
    ]
    if not activites_valides:
        return 0.0

    poids = [float(a.quantite_prevue) for a in activites_valides]
    total_poids = sum(poids)
    if total_poids <= 0:
        return 0.0

    avancements = [calculer_avancement_physique_activite(a) for a in activites_valides]
    somme = sum(av * p for av, p in zip(avancements, poids, strict=True))
    return float(round(somme / total_poids, 2))


def ponderer_lots_par_budget(lots) -> float:
    """Calcule l'avancement physique de lots pondéré par budget (SFD F3 §4.3, RG-F3-05).

    Seuls les lots actifs, non supprimés, et disposant d'un budget initial > 0 sont inclus.
    Retourne 0.0 si aucun lot n'a de budget.
    """
    lots_iterable = lots.all() if hasattr(lots, "all") else lots
    lots_actifs = [
        lot for lot in lots_iterable
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]
    lots_budgetes = [
        lot for lot in lots_actifs
        if getattr(lot, "budget_initial_montant", None) is not None
        and lot.budget_initial_montant > 0
    ]
    if not lots_budgetes:
        return 0.0

    poids = [float(lot.budget_initial_montant) for lot in lots_budgetes]
    total_poids = sum(poids)
    if total_poids <= 0:
        return 0.0

    avancements = [calculer_avancement_physique_lot(lot) for lot in lots_budgetes]
    somme = sum(av * p for av, p in zip(avancements, poids, strict=True))
    return float(round(somme / total_poids, 2))


def calculer_avancement_physique_projet(projet) -> tuple[float, str]:
    """Calcule l'avancement physique du projet (SFD F3 §4.3, RG-F3-05).

    Moyenne des lots actifs non supprimés, pondérée par lot.budget_initial_montant.
    Les lots sans budget (> 0) sont exclus du calcul.
    Retourne toujours (avancement, "BUDGET").
    Retourne (0.0, "BUDGET") si aucun lot n'a de budget.
    """
    avancement = ponderer_lots_par_budget(projet.lots.all())
    return avancement, "BUDGET"


def couverture_budget_projet(projet) -> dict[str, Any]:
    """Calcule la couverture budgétaire des lots par rapport au budget du projet (RG-F3-05).

    Retourne :
    {
        "lots_sans_budget": int,
        "part_budget_couverte": float | None,
    }
    - lots_sans_budget : nombre de lots actifs non supprimés sans budget > 0.
    - part_budget_couverte : part (en %, arrondie à 2 décimales) de
      projet.budget_initial_montant couverte par la somme des budgets des lots inclus (> 0),
      ou None si le projet n'a pas de budget > 0.
    """
    lots_actifs = [
        lot for lot in projet.lots.all()
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]

    lots_sans_budget = 0
    somme_budgets_inclus = Decimal("0")
    for lot in lots_actifs:
        b = getattr(lot, "budget_initial_montant", None)
        if b is not None and b > 0:
            somme_budgets_inclus += Decimal(str(b))
        else:
            lots_sans_budget += 1

    b_projet = getattr(projet, "budget_initial_montant", None)
    if b_projet is not None and Decimal(str(b_projet)) > Decimal("0"):
        ratio = (float(somme_budgets_inclus) / float(b_projet)) * 100.0
        part_budget_couverte = float(round(ratio, 2))
    else:
        part_budget_couverte = None

    return {
        "lots_sans_budget": lots_sans_budget,
        "part_budget_couverte": part_budget_couverte,
    }


def calculer_avancement_temporel_lot(
    lot,
    date_reference: date,
    jours_feries: Calendrier | set[date] | frozenset[date],
) -> float | None:
    """Calcule l'avancement temporel d'un lot : jours ouvrés écoulés / jours ouvrés totaux.

    Règle contractuelle (SFD F3 §4.4, Erratum E-1 & Décision 5) :
    - Paire baseline complète (date_debut_baseline et date_fin_baseline).
    - À défaut, paire prévisionnelle complète (date_debut_prevue et date_fin_prevue).
    - Si aucune des deux paires n'est complète, retourne None.
    - Bornes incluses au numérateur comme au dénominateur.
    - 0.0 % si date_reference < debut, 100.0 % si date_reference >= fin.
    """
    debut_base = getattr(lot, "date_debut_baseline", None)
    fin_base = getattr(lot, "date_fin_baseline", None)
    if debut_base and fin_base:
        debut, fin = debut_base, fin_base
    else:
        debut_prev = getattr(lot, "date_debut_prevue", None)
        fin_prev = getattr(lot, "date_fin_prevue", None)
        if debut_prev and fin_prev:
            debut, fin = debut_prev, fin_prev
        else:
            return None

    if date_reference < debut:
        return 0.0
    if date_reference >= fin:
        return 100.0

    total_ouvres = compter_jours_ouvres(debut, fin, jours_feries)
    if total_ouvres <= 0:
        return 100.0

    ecoules_ouvres = compter_jours_ouvres(debut, date_reference, jours_feries)
    ratio = (ecoules_ouvres / total_ouvres) * 100.0
    return float(round(max(0.0, min(100.0, ratio)), 2))


def calculer_avancement_temporel_projet(
    projet,
    date_reference: date,
    jours_feries: Calendrier | set[date] | frozenset[date],
) -> tuple[float, list[str]]:
    """Calcule l'avancement temporel consolidé du projet (SFD F3 §4.4, RG-F3-04).

    Moyenne des lots actifs non supprimés, pondérée par lot.budget_initial_montant (> 0).
    Seuls les lots disposant d'un budget > 0 et d'un avancement temporel non None sont retenus.
    Pour chaque lot actif non supprimé dont l'avancement temporel est None, ajoute
    l'avertissement LOT_SANS_DATES:<code>.
    Retourne (avancement, avertissements). Retourne (0.0, avertissements) si aucun lot n'est retenu.
    """
    avertissements: list[str] = []
    lots_iterable = projet.lots.all() if hasattr(projet.lots, "all") else projet.lots
    lots_actifs = [
        lot for lot in lots_iterable
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]
    if not lots_actifs:
        return 0.0, avertissements

    lots_retenus: list[tuple[Any, float]] = []
    for lot in lots_actifs:
        temp = calculer_avancement_temporel_lot(lot, date_reference, jours_feries)
        if temp is None:
            code = getattr(lot, "code", "")
            avertissements.append(f"LOT_SANS_DATES:{code}")
            continue

        budget = getattr(lot, "budget_initial_montant", None)
        if budget is not None and budget > 0:
            lots_retenus.append((lot, temp))

    if not lots_retenus:
        return 0.0, avertissements

    poids = [float(lot.budget_initial_montant) for lot, _ in lots_retenus]
    total_poids = sum(poids)
    if total_poids <= 0:
        return 0.0, avertissements

    somme = sum(temp * p for (_, temp), p in zip(lots_retenus, poids, strict=True))
    return float(round(somme / total_poids, 2)), avertissements


def calculer_delta_lot(
    lot,
    date_reference: date,
    calendrier: Calendrier | set[date] | frozenset[date],
) -> float | None:
    """Calcule l'écart d'avancement d'un lot (Formule 5, SFD F3 §4.5).

    Delta = avancement temporel (Formule 4) - avancement physique (Formule 2).
    Arrondi à 2 décimales. Un résultat positif signifie un retard.
    Retourne None si l'avancement temporel est None (absence de dates contractuelles).
    """
    temp = calculer_avancement_temporel_lot(lot, date_reference, calendrier)
    if temp is None:
        return None
    phys = calculer_avancement_physique_lot(lot)
    return float(round(temp - phys, 2))


def calculer_delta_projet(
    projet,
    date_reference: date,
    calendrier: Calendrier | set[date] | frozenset[date],
) -> float:
    """Calcule l'écart d'avancement consolidé d'un projet (Formule 5, SFD F3 §4.5).

    Delta = avancement temporel (Formule 4) - avancement physique (Formule 3).
    Arrondi à 2 décimales. Un résultat positif signifie un retard.
    """
    temp, _ = calculer_avancement_temporel_projet(projet, date_reference, calendrier)
    phys, _ = calculer_avancement_physique_projet(projet)
    return float(round(temp - phys, 2))


def determiner_badge_brut(score: int) -> str:
    """Détermine le badge de santé (VERT, ORANGE, ROUGE) selon les seuils existants.

    Seuils configurés :
    - score >= settings.SANTE_SEUIL_VERT (80)   -> VERT
    - score >= settings.SANTE_SEUIL_ORANGE (50) -> ORANGE
    - score < settings.SANTE_SEUIL_ORANGE (50)  -> ROUGE
    """
    seuil_vert = getattr(settings, "SANTE_SEUIL_VERT", 80)
    seuil_orange = getattr(settings, "SANTE_SEUIL_ORANGE", 50)

    if score >= seuil_vert:
        return str(BadgeSante.VERT)
    if score >= seuil_orange:
        return str(BadgeSante.ORANGE)
    return str(BadgeSante.ROUGE)


determiner_badge = determiner_badge_brut
