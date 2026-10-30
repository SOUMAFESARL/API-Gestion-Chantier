"""La courbe en S : le prévu, le réel, et la fin estimée (décision du 30/10/2026).

- **Le prévu** se calcule à partir des dates et des montants : à chaque date, l'avancement
  temporel du projet (ou de la case), pesé par la valeur comme le physique.
- **Le réel** se lit dans les relevés de chaque nuit (`PointAvancement`), plus la valeur du jour.
- **La fin estimée** prolonge le rythme des 4 dernières semaines. Elle est seulement affichée,
  jamais appliquée aux dates. Sans progression sur la période, il n'y a pas d'estimation.

On relève le projet et les cases suivies : les niveaux cochés « alerter », à défaut les racines.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.projets.models import Element, PointAvancement
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.indicateurs_temporels import calendrier_pour_elements
from apps.projets.services.sante_calculs import (
    calculer_arbre,
    calculer_avancement_temporel_element,
    calculer_temporels_arbre,
    resultat_projet,
)

__all__ = ["courbe", "enregistrer_releve"]

FENETRE_RYTHME = 28
PAS_PREVU = 7


def _temporel_projet(projet, arbre, resultats, temporels, jour, calendrier) -> float | None:
    """La même règle que `calculer_avancement_temporel_projet`, sur un arbre déjà calculé."""
    retenues = [
        (temporels.get(r.pk), resultats[r.pk].poids)
        for r in arbre.racines()
        if r.est_actif
        and temporels.get(r.pk) is not None
        and resultats.get(r.pk)
        and resultats[r.pk].poids
    ]
    if retenues:
        total = sum(p for _, p in retenues)
        return float(round(sum(Decimal(str(t)) * p for t, p in retenues) / total, 2))
    return calculer_avancement_temporel_element(projet, jour, calendrier)


def _cases_suivies(arbre):
    from apps.projets.services.machine_etats import cases_suivies

    return cases_suivies(arbre)


def enregistrer_releve(projet, jour: date | None = None) -> int:
    """Le relevé de la nuit : le projet et ses cases suivies. Rend le nombre de points écrits."""
    jour = jour or timezone.localdate()
    arbre = charger_arbre(projet, actifs_seulement=True)
    if not arbre.elements:
        return 0
    resultats = calculer_arbre(arbre)
    calendrier = calendrier_pour_elements([projet, *arbre.elements], jour)
    temporels = calculer_temporels_arbre(arbre, resultats, jour, calendrier)
    points = [
        (
            None,
            resultat_projet(projet, arbre, resultats).physique,
            _temporel_projet(projet, arbre, resultats, temporels, jour, calendrier),
        )
    ]
    for case in _cases_suivies(arbre):
        resultat = resultats.get(case.pk)
        points.append((case, resultat.physique if resultat else None, temporels.get(case.pk)))
    for element, physique, temporel in points:
        PointAvancement.objects.update_or_create(
            projet=projet,
            element=element,
            jour=jour,
            defaults={
                "physique": None if physique is None else Decimal(str(round(physique, 2))),
                "temporel": None if temporel is None else Decimal(str(round(temporel, 2))),
            },
        )
    return len(points)


def _bornes(objet, arbre=None) -> tuple[date | None, date | None]:
    """Les dates de l'objet ; pour une case qui n'en a pas, l'étendue de ses tâches."""
    debut = objet.date_debut_baseline or objet.date_debut_prevue
    fin = max([d for d in (objet.date_fin_prevue, objet.date_fin_baseline) if d], default=None)
    if arbre is not None and isinstance(objet, Element) and not (debut and fin):
        dessous = [e for e in arbre.descendants(objet) if e.est_actif]
        debuts = [e.date_debut_baseline or e.date_debut_prevue for e in dessous]
        fins = [e.date_fin_prevue or e.date_fin_baseline for e in dessous]
        debut = debut or min([d for d in debuts if d], default=None)
        fin = fin or max([d for d in fins if d], default=None)
    return debut, fin


def courbe(projet, element: Element | None = None, aujourdhui: date | None = None) -> dict:
    """Le prévu, le réel et la fin estimée, pour le projet ou pour une case."""
    aujourdhui = aujourdhui or timezone.localdate()
    arbre = charger_arbre(projet, actifs_seulement=True)
    resultats = calculer_arbre(arbre)
    cible = element or projet
    debut, fin = _bornes(cible, arbre)

    def physique_actuel():
        if element is None:
            return resultat_projet(projet, arbre, resultats).physique
        resultat = resultats.get(element.pk)
        return resultat.physique if resultat else None

    # Le prévu, une valeur par semaine du début à la fin, plus la fin elle-même.
    prevu = []
    if debut and fin and fin >= debut:
        calendrier = calendrier_pour_elements([projet, *arbre.elements], aujourdhui)
        jours = [debut + timedelta(days=n) for n in range(0, (fin - debut).days + 1, PAS_PREVU)]
        if jours[-1] != fin:
            jours.append(fin)
        for jour in jours:
            temporels = calculer_temporels_arbre(arbre, resultats, jour, calendrier)
            valeur = (
                _temporel_projet(projet, arbre, resultats, temporels, jour, calendrier)
                if element is None
                else temporels.get(element.pk)
            )
            prevu.append({"date": jour, "valeur": None if valeur is None else round(valeur, 1)})

    # Le réel : les relevés de nuit, puis la valeur du jour.
    releves = PointAvancement.objects.filter(projet=projet, element=element).order_by("jour")
    reel = [
        {"date": p.jour, "valeur": float(p.physique)}
        for p in releves
        if p.physique is not None and p.jour < aujourdhui
    ]
    actuel = physique_actuel()
    if actuel is not None:
        reel.append({"date": aujourdhui, "valeur": round(actuel, 1)})

    # La fin estimée : le rythme des 4 dernières semaines, prolongé jusqu'à 100 %.
    fin_estimee, rythme = None, None
    depart = aujourdhui - timedelta(days=FENETRE_RYTHME)
    anciens = [p for p in reel if p["date"] >= depart]
    if actuel is not None and len(anciens) >= 2:
        premier = anciens[0]
        ecart_jours = (aujourdhui - premier["date"]).days
        if ecart_jours >= 7:
            par_jour = (actuel - premier["valeur"]) / ecart_jours
            rythme = round(par_jour * 7, 2)
            if par_jour > 0 and actuel < 100:
                fin_estimee = aujourdhui + timedelta(days=math.ceil((100 - actuel) / par_jour))
    return {
        "element_id": str(element.pk) if element else None,
        "debut": debut,
        "fin_prevue": cible.date_fin_prevue,
        "fin_contractuelle": cible.date_fin_contractuelle,
        "prevu": prevu,
        "reel": reel,
        # Points par semaine sur les 4 dernières semaines ; None : pas assez de relevés.
        "rythme_par_semaine": rythme,
        # Affichée seulement, jamais appliquée aux dates.
        "fin_estimee": fin_estimee,
    }
