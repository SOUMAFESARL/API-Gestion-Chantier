"""Moteur de calcul pur pour les avancements et le calendrier d'entreprise.

Fonctions pures, déterministes et testables unitairement :
- Formule 1 : physique d'une feuille (quantité, pourcentage déclaré ou jalon).
- Formules 2 et 3 : physique d'un parent et du projet, moyenne des enfants pondérée par le
  montant (décisions v1.2 du découpage, §8 et §9).
- Formule 4 : temporel d'une case et du projet (jours ouvrés écoulés sur la baseline).
- Formule 5 : écart (temporel - physique), pour chaque case et pour le projet.
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
    "ResultatCase",
    "calculer_arbre",
    "calculer_avancement_physique_activite",
    "calculer_avancement_physique_feuille",
    "calculer_avancement_physique_projet",
    "calculer_avancement_temporel_element",
    "calculer_avancement_temporel_projet",
    "calculer_delta_element",
    "calculer_delta_projet",
    "calculer_temporels_arbre",
    "calendrier_entreprise",
    "compter_jours_ouvres",
    "couverture_budget_projet",
    "determiner_badge",
    "determiner_badge_brut",
    "est_jour_ouvre",
    "obtenir_jours_feries_ci",
    "resultat_projet",
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
# Avancements physiques et temporels sur l'arbre (F3 généralisée, décisions v1.2 §8 et §9)
# --------------------------------------------------------------------------
#
# **Le principe ne change pas** : on mesure sur les cases du bas (les feuilles) et une moyenne
# pondérée remonte jusqu'au projet. Deux différences : le poids est partout le **montant**
# (les quantités ne s'additionnent pas entre unités), et le nombre d'étages est libre.
#
# | Situation                                  | Poids         | Physique du parent              |
# | Feuille avec un montant                    | son montant   | —                               |
# | Tous les enfants ont un poids              | leur somme    | moyenne pondérée des enfants    |
# | Enfants partiellement chiffrés + enveloppe | l'enveloppe   | Σ(physique x poids) / enveloppe |
# | Partiellement chiffrés, sans enveloppe     | aucun         | sur les chiffrés, « partiel »   |
# | Aucun montant connu                        | aucun         | « indisponible » (None)         |


class ResultatCase:
    """Le calcul d'une case : son poids, son physique, et ce qui le rend partiel."""

    __slots__ = ("exclus", "partiel", "physique", "poids")

    def __init__(self, poids, physique, partiel=False, exclus=0):
        self.poids = poids
        self.physique = physique
        self.partiel = partiel
        self.exclus = exclus


def calculer_avancement_physique_feuille(feuille) -> float:
    """F3 formule 1 : quantité réalisée / quantité prévue, ou pourcentage déclaré, ou jalon.

    100 % si la feuille est clôturée. Plafonné à 100 % (un dépassement s'affiche ailleurs), 0 %
    tant qu'une feuille en quantité n'a pas de quantité prévue.
    """
    if getattr(feuille, "cloture", False) or getattr(feuille, "statut", None) == StatutActivite.CLOTURE:
        return 100.0
    mode = getattr(feuille, "mode_mesure", "QUANTITE")
    if mode == "POURCENTAGE":
        return float(round(max(0.0, min(100.0, float(feuille.pourcentage_declare or 0))), 2))
    if mode == "JALON":
        return 0.0
    q_prevue = getattr(feuille, "quantite_prevue", None) or 0
    if q_prevue <= 0:
        return 0.0
    q_realisee = getattr(feuille, "quantite_realisee", None) or 0
    pourcentage = (float(q_realisee) / float(q_prevue)) * 100.0
    return float(round(max(0.0, min(100.0, pourcentage)), 2))


# Rétrocompatibilité des appels : une activité d'hier est une feuille d'aujourd'hui.
calculer_avancement_physique_activite = calculer_avancement_physique_feuille


def _poids_feuille(feuille):
    montant = getattr(feuille, "montant", None)
    return Decimal(montant) if montant and montant > 0 else None


def _combiner(enfants: list[ResultatCase], enveloppe) -> ResultatCase:
    """Le poids et le physique d'un parent à partir de ses enfants (§8)."""
    enveloppe = Decimal(enveloppe) if enveloppe and enveloppe > 0 else None
    chiffres = [r for r in enfants if r.poids is not None and r.physique is not None]
    exclus = len(enfants) - len(chiffres) + sum(r.exclus for r in enfants)
    partiel_enfant = any(r.partiel for r in chiffres)
    somme_poids = sum((r.poids for r in chiffres), Decimal(0))
    somme_ponderee = sum((Decimal(str(r.physique)) * r.poids for r in chiffres), Decimal(0))

    if chiffres and len(chiffres) == len(enfants):
        physique = float(round(somme_ponderee / somme_poids, 2)) if somme_poids else 0.0
        return ResultatCase(somme_poids, physique, partiel_enfant, exclus)
    if enveloppe is not None:
        physique = float(round(min(Decimal(100), somme_ponderee / enveloppe), 2))
        return ResultatCase(enveloppe, physique, partiel_enfant, exclus)
    if chiffres:
        physique = float(round(somme_ponderee / somme_poids, 2)) if somme_poids else 0.0
        return ResultatCase(None, physique, True, exclus)
    return ResultatCase(None, None, False, exclus)


def calculer_arbre(arbre) -> dict:
    """Le résultat de chaque case active de l'arbre, des feuilles vers les racines.

    Rend `{element_id: ResultatCase}`. Une case désactivée sort des calculs (§10).
    """
    resultats: dict = {}

    def visiter(element) -> ResultatCase:
        enfants = arbre.enfants_actifs(element)
        if not enfants:
            poids = _poids_feuille(element)
            physique = calculer_avancement_physique_feuille(element)
            # Sans montant, la feuille a un physique mais ne pèse rien au-dessus d'elle.
            resultat = ResultatCase(poids, physique)
        else:
            resultat = _combiner([visiter(e) for e in enfants], element.enveloppe)
        resultats[element.pk] = resultat
        return resultat

    for racine in arbre.racines():
        if racine.est_actif:
            visiter(racine)
    return resultats


def resultat_projet(projet, arbre=None, resultats=None) -> ResultatCase:
    """La règle de tout parent, appliquée au projet ; son budget tient lieu d'enveloppe."""
    from apps.projets.selectors.arbre import charger_arbre

    arbre = arbre or charger_arbre(projet)
    resultats = resultats if resultats is not None else calculer_arbre(arbre)
    racines = [r for r in arbre.racines() if r.est_actif]
    if not racines:
        return ResultatCase(None, None)
    return _combiner([resultats[r.pk] for r in racines], projet.budget_initial_montant)


def calculer_avancement_physique_projet(projet) -> tuple[float, str]:
    """F3 formule 3 : la règle de tout parent. Rend 0.0 quand l'avancement est indisponible —
    le stockage du projet reste un nombre ; l'arbre, lui, dit « indisponible »."""
    resultat = resultat_projet(projet)
    return (resultat.physique if resultat.physique is not None else 0.0), "MONTANT"


def couverture_budget_projet(projet) -> dict[str, Any]:
    """Combien de feuilles n'ont pas de montant, et quelle part du budget les montants couvrent."""
    from apps.projets.selectors.arbre import charger_arbre

    arbre = charger_arbre(projet)
    feuilles = arbre.feuilles()
    sans_montant = sum(1 for f in feuilles if not f.montant)
    somme = sum((Decimal(f.montant) for f in feuilles if f.montant), Decimal(0))
    b_projet = getattr(projet, "budget_initial_montant", None)
    part = (
        float(round(float(somme) / float(b_projet) * 100.0, 2))
        if b_projet and Decimal(str(b_projet)) > 0
        else None
    )
    return {"feuilles_sans_montant": sans_montant, "part_budget_couverte": part}


def calculer_avancement_temporel_element(
    element,
    date_reference: date,
    jours_feries: Calendrier | set[date] | frozenset[date],
) -> float | None:
    """F3 formule 4 sur les dates propres d'une case : jours ouvrés écoulés / jours ouvrés totaux.

    Baseline complète d'abord, à défaut dates prévues ; None si aucune paire n'est complète.
    Bornes incluses ; 0 % avant le début, 100 % à partir de la fin.
    """
    debut_base = getattr(element, "date_debut_baseline", None)
    fin_base = getattr(element, "date_fin_baseline", None)
    if debut_base and fin_base:
        debut, fin = debut_base, fin_base
    else:
        debut_prev = getattr(element, "date_debut_prevue", None)
        fin_prev = getattr(element, "date_fin_prevue", None)
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


def calculer_temporels_arbre(arbre, resultats, date_reference, calendrier) -> dict:
    """Le temporel de chaque case active : sur ses dates pour une feuille ; pour un parent,
    la moyenne de ses enfants avec les mêmes poids que le physique — ou ses propres dates si ses
    enfants sont incomplètement chiffrés ou datés (§9, formule 4)."""
    temporels: dict = {}

    def visiter(element):
        enfants = arbre.enfants_actifs(element)
        propre = calculer_avancement_temporel_element(element, date_reference, calendrier)
        if not enfants:
            temporels[element.pk] = propre
            return propre
        valeurs = [(visiter(e), resultats.get(e.pk)) for e in enfants]
        complets = all(t is not None and r and r.poids for t, r in valeurs)
        if complets:
            total = sum(r.poids for _, r in valeurs)
            moyenne = sum(Decimal(str(t)) * r.poids for t, r in valeurs) / total if total else 0
            temporels[element.pk] = float(round(moyenne, 2))
        else:
            temporels[element.pk] = propre
        return temporels[element.pk]

    for racine in arbre.racines():
        if racine.est_actif:
            visiter(racine)
    return temporels


def calculer_avancement_temporel_projet(
    projet,
    date_reference: date,
    jours_feries: Calendrier | set[date] | frozenset[date],
) -> tuple[float, list[str]]:
    """Temporel du projet : moyenne des racines pondérée par leur poids ; à défaut, ses dates.

    Rend aussi les avertissements `CASE_SANS_DATES:<intitulé>` des racines sans dates.
    """
    from apps.projets.selectors.arbre import charger_arbre

    arbre = charger_arbre(projet)
    resultats = calculer_arbre(arbre)
    temporels = calculer_temporels_arbre(arbre, resultats, date_reference, jours_feries)
    avertissements = []
    retenues = []
    for racine in arbre.racines():
        if not racine.est_actif:
            continue
        t = temporels.get(racine.pk)
        if t is None:
            avertissements.append(f"CASE_SANS_DATES:{racine.libelle}")
            continue
        r = resultats.get(racine.pk)
        if r and r.poids:
            retenues.append((t, r.poids))
    if retenues:
        total = sum(p for _, p in retenues)
        valeur = sum(Decimal(str(t)) * p for t, p in retenues) / total
        return float(round(valeur, 2)), avertissements
    propre = calculer_avancement_temporel_element(projet, date_reference, jours_feries)
    return (propre if propre is not None else 0.0), avertissements


def calculer_deltas_arbre(arbre, resultats, date_reference, calendrier) -> dict:
    """F3 formule 5 pour chaque case : temporel de l'arbre - physique.

    Le temporel d'un parent vient de ses enfants (`calculer_temporels_arbre`) : le tableau de
    démarrage ne date souvent que les feuilles, et un lot sans dates propres se juge quand même.
    None pour une case sans temporel.
    """
    temporels = calculer_temporels_arbre(arbre, resultats, date_reference, calendrier)
    deltas = {}
    for pk, temporel in temporels.items():
        resultat = resultats.get(pk)
        physique = resultat.physique if resultat and resultat.physique is not None else 0.0
        deltas[pk] = None if temporel is None else float(round(temporel - physique, 2))
    return deltas


def calculer_delta_element(element, date_reference, calendrier, physique=None) -> float | None:
    """F3 formule 5 : temporel - physique, d'une case. Positif = retard ; None sans dates."""
    temp = calculer_avancement_temporel_element(element, date_reference, calendrier)
    if temp is None:
        return None
    if physique is None:
        physique = float(getattr(element, "avancement", None) or 0)
    return float(round(temp - physique, 2))


def calculer_delta_projet(
    projet,
    date_reference: date,
    calendrier: Calendrier | set[date] | frozenset[date],
) -> float:
    """F3 formule 5 du projet : temporel - physique. Positif = retard."""
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
