"""Service du calendrier d'entreprise pour les jours ouvrés.

SFD F3 §6 & Erratum v1.0.1 (E-4).

Règle des trois couches (de la plus forte à la plus faible) :
1. Exceptions de l'entreprise (ExceptionCalendrier) : ouvré ou non ouvré pour une date précise.
2. Jours fériés nationaux (referentiels.JourFerie, schéma public).
3. Semaine type de l'entreprise (SemaineType, lundi à vendredi par défaut).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from apps.projets.models.calendrier import ExceptionCalendrier, SemaineType

__all__ = [
    "CALENDRIER_PAR_DEFAUT_SEMAINE",
    "Calendrier",
    "calendrier_entreprise",
    "calendrier_national_est_incomplet",
]

CALENDRIER_PAR_DEFAUT_SEMAINE: frozenset[int] = frozenset({0, 1, 2, 3, 4})


@dataclass(frozen=True)
class Calendrier:
    """Calendrier pur et figé d'une entreprise pour une période donnée.

    jours_semaine : ensemble des jours de la semaine travaillés (0 = lundi, ..., 6 = dimanche).
    feries : ensemble des dates de jours fériés nationaux.
    exceptions : dictionnaire date -> bool (True si ouvré, False si chômé).
    est_incomplet : booléen indiquant si les données nationales sont incomplètes.
    """

    jours_semaine: frozenset[int]
    feries: frozenset[date]
    exceptions: dict[date, bool]
    est_incomplet: bool = False

    def est_ouvre(self, d: date) -> bool:
        """Détermine si la date d est ouvrée selon la hiérarchie des 3 couches.

        Règle :
        1. Si d est dans exceptions, la valeur de l'exception (True ou False).
        2. Sinon, si d est un jour férié national, False.
        3. Sinon, d.weekday() in jours_semaine.
        """
        if d in self.exceptions:
            return self.exceptions[d]
        if d in self.feries:
            return False
        return d.weekday() in self.jours_semaine


def calendrier_national_est_incomplet(calendrier: Calendrier) -> bool:
    """Indique si le calendrier national est incomplet pour la période considérée."""
    return getattr(calendrier, "est_incomplet", False)


def calendrier_entreprise(debut: date, fin: date) -> Calendrier:
    """Construit le calendrier de l'entreprise courante pour la période [debut, fin].

    Composé des trois couches :
    - Semaine type par SemaineType.courante().jours_travailles().
    - Fériés nationaux par obtenir_jours_feries_ci sur les années de debut à fin.
    - Exceptions non supprimées de l'entreprise sur l'intervalle [debut, fin].
    """
    from apps.projets.services.sante_calculs import obtenir_jours_feries_ci

    d_min, d_max = (debut, fin) if debut <= fin else (fin, debut)
    feries_set, est_incomplet = obtenir_jours_feries_ci(d_min.year, d_max.year)

    semaine = SemaineType.courante().jours_travailles()

    exceptions_qs = ExceptionCalendrier.objects.filter(
        supprime_le__isnull=True,
        date__gte=d_min,
        date__lte=d_max,
    )
    exceptions = {e.date: e.ouvre for e in exceptions_qs}

    return Calendrier(
        jours_semaine=semaine,
        feries=frozenset(feries_set),
        exceptions=exceptions,
        est_incomplet=est_incomplet,
    )
