"""La courbe en S : le prévu, le réel, et la fin estimée (décision du 30/10/2026).

- **Le prévu** se calcule à partir des dates et des montants du découpage : à chaque date,
  l'avancement temporel du projet (ou de la case), pesé par la valeur comme le physique (ou en
  moyenne simple si le découpage n'est pas chiffré), avec repli sur le projet si le découpage
  n'a aucune date ou des dates partielles.
- **Le réel** se lit dans les relevés (`PointAvancement`), plus la valeur du jour.
- **La fin estimée** prolonge le rythme des 4 dernières semaines. Elle est seulement affichée,
  jamais appliquée aux dates. Sans progression sur la période, il n'y a pas d'estimation.

Couverture des relevés :
- le projet entier (`element=None`) ;
- TOUS les éléments actifs de niveau 1 (`parent_id=None`), MÊME s'ils sont feuilles sans enfant ;
- TOUS les éléments actifs des autres niveaux ayant au moins un enfant (`not arbre.est_feuille(e)`).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.projets.models import Element, PointAvancement
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.indicateurs_temporels import calendrier_pour_elements
from apps.projets.services.sante_calculs import (
    calculer_arbre,
    calculer_avancement_temporel_element,
    calculer_temporels_arbre,
    resultat_projet,
)

__all__ = ["cases_pour_courbe", "courbe", "enregistrer_releve"]

FENETRE_RYTHME = 28
PAS_PREVU = 7


def _dates_objet(objet) -> tuple[date | None, date | None]:
    """Dates de référence d'un projet ou d'un élément (baseline prioritaire au début)."""
    debut = objet.date_debut_baseline or objet.date_debut_prevue
    fin = max([d for d in (objet.date_fin_prevue, objet.date_fin_baseline) if d], default=None)
    return debut, fin


def _temporel_projet(projet, arbre, resultats, temporels, jour, calendrier) -> float | None:
    """Temporel du projet issu du découpage, adapté aux trois cas :
    - toutes les racines actives datées : moyenne pondérée (ou simple si non chiffrées) ;
    - dates partielles : combine les racines datées et le repli projet (s'il existe) pour les
      racines non datées, sinon moyenne sur les racines datées ;
    - aucune date dans le découpage : repli sur les dates du projet.
    """
    racines = [r for r in arbre.racines() if r.est_actif]
    propre_projet = calculer_avancement_temporel_element(projet, jour, calendrier)
    if not racines:
        return propre_projet

    avec_temporel = [(r, temporels.get(r.pk), resultats.get(r.pk)) for r in racines]
    datees = [(r, t, res) for r, t, res in avec_temporel if t is not None]
    if not datees:
        return propre_projet

    if len(datees) < len(avec_temporel) and propre_projet is not None:
        effectives = [
            (r, t if t is not None else propre_projet, res) for r, t, res in avec_temporel
        ]
    else:
        effectives = datees

    ponderees = [(t, res.poids) for _, t, res in effectives if res and res.poids]
    if ponderees:
        total = sum(p for _, p in ponderees)
        return float(round(sum(Decimal(str(t)) * p for t, p in ponderees) / total, 2))

    moyenne = sum(Decimal(str(t)) for _, t, _ in effectives) / Decimal(len(effectives))
    return float(round(moyenne, 2))


def _cases_suivies(arbre):
    from apps.projets.services.machine_etats import cases_suivies

    return cases_suivies(arbre)


def cases_pour_courbe(arbre) -> list[Element]:
    """Les cases suivies par la courbe en S :
    - tous les éléments actifs de niveau 1 (`parent_id is None`), même feuilles ;
    - tous les éléments actifs d'autres niveaux ayant au moins un enfant actif ;
    - plus les éventuelles cases suivies (`cases_suivies`).
    """
    selection: list[Element] = []
    vus = set()
    for e in arbre.elements:
        if not e.est_actif:
            continue
        if e.parent_id is None or not arbre.est_feuille(e):
            selection.append(e)
            vus.add(e.pk)
    for c in _cases_suivies(arbre):
        if c.est_actif and c.pk not in vus:
            selection.append(c)
            vus.add(c.pk)
    return selection


def enregistrer_releve(projet, jour: date | None = None) -> int:
    """Enregistre le relevé d'avancement du projet, de tous les éléments actifs de niveau 1
    (même feuilles) et de toutes les cases parentes actives."""
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
    for case in cases_pour_courbe(arbre):
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


def _bornes_element(element: Element, arbre=None) -> tuple[date | None, date | None]:
    """Bornes prévues d'une case : ses dates propres et/ou l'enveloppe de ses descendants actifs."""
    d_propre, f_propre = _dates_objet(element)
    if arbre is None:
        return d_propre, f_propre
    dessous = [e for e in arbre.descendants(element) if e.est_actif]
    if not dessous:
        return d_propre, f_propre
    debuts = [d for d, _ in (_dates_objet(e) for e in dessous) if d]
    fins = [f for _, f in (_dates_objet(e) for e in dessous) if f]
    d_sub = min(debuts) if debuts else None
    f_sub = max(fins) if fins else None
    if element.dates_calculees or not (d_propre and f_propre):
        debut = d_sub or d_propre
        fin = f_sub or f_propre
    else:
        debut = min([d for d in (d_propre, d_sub) if d], default=None)
        fin = max([f for f in (f_propre, f_sub) if f], default=None)
    return debut, fin


def _bornes(objet, arbre=None) -> tuple[date | None, date | None]:
    """Les bornes prévues pour la courbe en S.

    - Pour une case (`Element`) : ses dates ou l'enveloppe de ses descendants actifs.
    - Pour le projet : proviennent du découpage :
      * si toutes les racines actives du découpage ont des dates -> enveloppe du découpage ;
      * si aucune case active du découpage n'a de dates -> repli sur les dates du projet ;
      * si dates partielles -> union avec le projet s'il est daté, sinon enveloppe des cases datées.
    """
    if isinstance(objet, Element):
        return _bornes_element(objet, arbre)

    d_proj, f_proj = _dates_objet(objet)
    if arbre is None:
        return d_proj, f_proj

    actifs = [e for e in arbre.elements if e.est_actif]
    racines = [r for r in arbre.racines() if r.est_actif]
    if not actifs or not racines:
        return d_proj, f_proj

    debuts_dec = [d for d, _ in (_dates_objet(e) for e in actifs) if d]
    fins_dec = [f for _, f in (_dates_objet(e) for e in actifs) if f]
    if not debuts_dec or not fins_dec:
        return d_proj, f_proj

    racines_bornes = [_bornes_element(r, arbre) for r in racines]
    toutes_racines_datees = all(d is not None and f is not None for d, f in racines_bornes)
    if toutes_racines_datees:
        return min(debuts_dec), max(fins_dec)

    # Dates partielles : si le projet porte ses propres dates, couvrir les deux pour ne pas
    # tronquer la courbe avant la fin prévue des branches non datées.
    if d_proj and f_proj:
        return min([*debuts_dec, d_proj]), max([*fins_dec, f_proj])
    return min(debuts_dec), max(fins_dec)


def _fin_prevue_courbe(
    projet, element: Element | None, arbre, fin_borne: date | None
) -> date | None:
    """Date de fin prévue cohérente avec la source retenue (découpage prioritaire, repli projet)."""
    if element is not None:
        return element.date_fin_prevue or fin_borne
    actifs = [e for e in arbre.elements if e.est_actif]
    racines = [r for r in arbre.racines() if r.est_actif]
    fins_dec = [e.date_fin_prevue for e in actifs if e.date_fin_prevue]
    if not fins_dec:
        return projet.date_fin_prevue
    racines_bornes = [_bornes_element(r, arbre) for r in racines]
    if racines and all(d is not None and f is not None for d, f in racines_bornes):
        return max(fins_dec)
    if projet.date_fin_prevue:
        return max(*fins_dec, projet.date_fin_prevue)
    return max(fins_dec)


def courbe(projet, element: Element | None = None, aujourdhui: date | None = None) -> dict:
    """Le prévu, le réel et la fin estimée, pour le projet ou pour une case."""
    aujourdhui = aujourdhui or timezone.localdate()
    arbre = charger_arbre(projet, actifs_seulement=True)
    resultats = calculer_arbre(arbre)
    if element is not None:
        element = arbre.par_id.get(element.pk, element)
    cible = element or projet
    debut, fin = _bornes(cible, arbre)
    fin_prevue = _fin_prevue_courbe(projet, element, arbre, fin)

    def physique_actuel():
        if element is None:
            return resultat_projet(projet, arbre, resultats).physique
        resultat = resultats.get(element.pk)
        return resultat.physique if resultat else None

    # Le prévu, une valeur par semaine du début à la fin, plus la fin elle-même.
    prevu = []
    if debut and fin and fin >= debut:
        calendrier = calendrier_entreprise(min(debut, aujourdhui), max(fin, aujourdhui))
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

    # Le réel : relevés passés (direct ou consolidation nocturne), puis valeur du jour.
    releves = PointAvancement.objects.filter(projet=projet, element=element).order_by("jour")
    if not releves.filter(jour__lt=aujourdhui).exists():
        from apps.chantier.models import RapportJournalier
        from apps.core.enums import StatutRapport

        dates_rapports = list(
            RapportJournalier.objects.filter(
                projet=projet,
                statut=StatutRapport.APPROUVE,
                supprime_le__isnull=True,
                date_rapport__lt=aujourdhui,
            )
            .values_list("date_rapport", flat=True)
            .distinct()
            .order_by("date_rapport")
        )
        for d in dates_rapports:
            enregistrer_releve(projet, jour=d)
        if not releves.filter(jour=aujourdhui).exists():
            enregistrer_releve(projet, jour=aujourdhui)
        releves = PointAvancement.objects.filter(projet=projet, element=element).order_by("jour")

    reel = [
        {"date": p.jour, "valeur": float(p.physique)}
        for p in releves
        if p.physique is not None and p.jour < aujourdhui
    ]
    actuel = physique_actuel()
    if actuel is not None:
        # Point d'ancrage à 0 % au début du projet/case pour tracer la droite dès le 1er relevé.
        if debut and debut < aujourdhui and (not reel or reel[0]["date"] > debut):
            reel.insert(0, {"date": debut, "valeur": 0.0})
        reel.append({"date": aujourdhui, "valeur": round(actuel, 1)})

    # La fin estimée : rythme des 4 dernières semaines (ou depuis le dernier point), jusqu'à 100 %.
    fin_estimee, rythme = None, None
    depart = aujourdhui - timedelta(days=FENETRE_RYTHME)
    anciens = [p for p in reel if p["date"] >= depart]
    if len(anciens) < 2 and len(reel) >= 2:
        anciens = [reel[-2], reel[-1]]
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
        "fin_prevue": fin_prevue,
        "fin_contractuelle": cible.date_fin_contractuelle,
        "prevu": prevu,
        "reel": reel,
        # Points par semaine sur les 4 dernières semaines ; None : pas assez de relevés.
        "rythme_par_semaine": rythme,
        # Affichée seulement, jamais appliquée aux dates.
        "fin_estimee": fin_estimee,
    }
