"""Service de calcul à la volée des indicateurs temporels d'un projet et d'une case de l'arbre.

SFD F3 §4.4, §4.5, RG-F3-04 & Erratum v1.0.1 (E-4).

Les valeurs d'avancement temporel et de delta de retard ne sont plus lues depuis
les champs stockés en base de données : elles sont calculées dynamiquement à la lecture
selon les jours ouvrés réels du calendrier d'entreprise.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone

from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.sante_calculs import (
    calculer_avancement_temporel_element,
    calculer_avancement_temporel_projet,
    calculer_delta_element,
    calculer_delta_projet,
)

__all__ = [
    "calendrier_pour_elements",
    "calendrier_pour_projets",
    "indicateurs_temporels_element",
    "indicateurs_temporels_projet",
]

CHAMPS_DATES = (
    "date_debut_baseline",
    "date_fin_baseline",
    "date_debut_prevue",
    "date_fin_prevue",
    "date_debut_reelle",
    "date_fin_reelle",
)


def _extraire_bornes_dates(objet: Any, date_ref: date) -> tuple[date, date]:
    """Les dates minimale et maximale d'un projet ou d'une case, date de référence comprise.

    Les cases de l'arbre s'inscrivent dans les dates de leur projet (le parent encadre, §11) :
    les dates du projet suffisent à borner le calendrier de tout son découpage.
    """
    dates: list[date] = [date_ref]
    for champ in CHAMPS_DATES:
        val = getattr(objet, champ, None)
        if isinstance(val, date):
            dates.append(val)
    return min(dates), max(dates)


_extraire_bornes_dates_projet = _extraire_bornes_dates


def indicateurs_temporels_projet(
    projet: Any,
    date_reference: date | None = None,
    calendrier: Any = None,
) -> dict[str, float]:
    """Calcule les indicateurs temporels consolidés d'un projet.

    Retourne :
        {"avancement_temporel": float, "delta_retard": float}
    """
    date_ref = date_reference if date_reference is not None else timezone.localdate()
    cal = calendrier
    if cal is None:
        debut, fin = _extraire_bornes_dates_projet(projet, date_ref)
        cal = calendrier_entreprise(debut, fin)

    av_temp, _ = calculer_avancement_temporel_projet(projet, date_ref, cal)
    delta = calculer_delta_projet(projet, date_ref, cal)

    return {
        "avancement_temporel": float(av_temp),
        "delta_retard": float(delta),
    }


def indicateurs_temporels_element(
    element: Any,
    date_reference: date | None = None,
    calendrier: Any = None,
    physique: float | None = None,
) -> dict[str, float | None]:
    """Les indicateurs temporels d'une case, sur ses propres dates.

    Retourne {"avancement_temporel": float | None, "delta_retard": float | None}.
    """
    date_ref = date_reference if date_reference is not None else timezone.localdate()
    cal = calendrier
    if cal is None:
        debut, fin = _extraire_bornes_dates(element, date_ref)
        cal = calendrier_entreprise(debut, fin)

    av_temp = calculer_avancement_temporel_element(element, date_ref, cal)
    delta = calculer_delta_element(element, date_ref, cal, physique)

    return {
        "avancement_temporel": float(av_temp) if av_temp is not None else None,
        "delta_retard": float(delta) if delta is not None else None,
    }


def calendrier_pour_projets(
    projets: Any,
    date_reference: date | None = None,
) -> Any:
    """Instancie un calendrier unique couvrant l'ensemble des projets et leurs lots."""
    date_ref = date_reference if date_reference is not None else timezone.localdate()
    dates_min: list[date] = [date_ref]
    dates_max: list[date] = [date_ref]

    for p in projets:
        d_min, d_max = _extraire_bornes_dates_projet(p, date_ref)
        dates_min.append(d_min)
        dates_max.append(d_max)

    return calendrier_entreprise(min(dates_min), max(dates_max))


def calendrier_pour_elements(
    elements: Any,
    date_reference: date | None = None,
) -> Any:
    """Instancie un calendrier unique couvrant un ensemble de cases."""
    date_ref = date_reference if date_reference is not None else timezone.localdate()
    dates_min: list[date] = [date_ref]
    dates_max: list[date] = [date_ref]

    for element in elements:
        d_min, d_max = _extraire_bornes_dates(element, date_ref)
        dates_min.append(d_min)
        dates_max.append(d_max)

    return calendrier_entreprise(min(dates_min), max(dates_max))
