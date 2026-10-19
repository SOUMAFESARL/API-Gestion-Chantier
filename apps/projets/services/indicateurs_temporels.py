"""Service de calcul à la volée des indicateurs temporels de projet et de lot.

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
    calculer_avancement_temporel_lot,
    calculer_avancement_temporel_projet,
    calculer_delta_lot,
    calculer_delta_projet,
)

__all__ = [
    "calendrier_pour_lots",
    "calendrier_pour_projets",
    "indicateurs_temporels_lot",
    "indicateurs_temporels_projet",
]


def _extraire_bornes_dates_projet(projet: Any, date_ref: date) -> tuple[date, date]:
    """Détermine les dates minimale et maximale pour instancier le calendrier.

    Couvre la date de référence et toutes les dates renseignées du projet et de ses lots.
    """
    dates: list[date] = [date_ref]

    for champ in (
        "date_debut_baseline",
        "date_fin_baseline",
        "date_debut_prevue",
        "date_fin_prevue",
        "date_debut_reelle",
        "date_fin_reelle",
    ):
        val = getattr(projet, champ, None)
        if isinstance(val, date):
            dates.append(val)

    lots_iterable = (
        projet.lots.all()
        if hasattr(projet, "lots") and hasattr(projet.lots, "all")
        else getattr(projet, "lots", [])
    )
    for lot in lots_iterable:
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None:
            for champ in (
                "date_debut_baseline",
                "date_fin_baseline",
                "date_debut_prevue",
                "date_fin_prevue",
                "date_debut_reelle",
                "date_fin_reelle",
            ):
                val = getattr(lot, champ, None)
                if isinstance(val, date):
                    dates.append(val)

    return min(dates), max(dates)


def _extraire_bornes_dates_lot(lot: Any, date_ref: date) -> tuple[date, date]:
    """Détermine les dates minimale et maximale pour instancier le calendrier.

    Couvre la date de référence et toutes les dates contractuelles ou réelles du lot.
    """
    dates: list[date] = [date_ref]
    for champ in (
        "date_debut_baseline",
        "date_fin_baseline",
        "date_debut_prevue",
        "date_fin_prevue",
        "date_debut_reelle",
        "date_fin_reelle",
    ):
        val = getattr(lot, champ, None)
        if isinstance(val, date):
            dates.append(val)

    return min(dates), max(dates)


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


def indicateurs_temporels_lot(
    lot: Any,
    date_reference: date | None = None,
    calendrier: Any = None,
) -> dict[str, float | None]:
    """Calcule les indicateurs temporels d'un lot.

    Retourne :
        {"avancement_temporel": float | None, "delta_retard": float | None}
    """
    date_ref = date_reference if date_reference is not None else timezone.localdate()
    cal = calendrier
    if cal is None:
        debut, fin = _extraire_bornes_dates_lot(lot, date_ref)
        cal = calendrier_entreprise(debut, fin)

    av_temp = calculer_avancement_temporel_lot(lot, date_ref, cal)
    delta = calculer_delta_lot(lot, date_ref, cal)

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


def calendrier_pour_lots(
    lots: Any,
    date_reference: date | None = None,
) -> Any:
    """Instancie un calendrier unique couvrant l'ensemble des lots."""
    date_ref = date_reference if date_reference is not None else timezone.localdate()
    dates_min: list[date] = [date_ref]
    dates_max: list[date] = [date_ref]

    for lot in lots:
        d_min, d_max = _extraire_bornes_dates_lot(lot, date_ref)
        dates_min.append(d_min)
        dates_max.append(d_max)

    return calendrier_entreprise(min(dates_min), max(dates_max))

