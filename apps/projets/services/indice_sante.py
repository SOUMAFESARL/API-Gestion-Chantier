"""Module de calcul de l'Indice de Santé de Projet — SFD F3 §4.6 (Formule 6).

Ce module implémente le moteur d'indice de santé synthétique (0 à 100) fondé
sur quatre dimensions fondamentales : Délais, Rapports journaliers, Blocages et
Incidents.

RAPPEL DES PALIERS (DÉCISIONS DU PILOTAGE) :
La SFD F3 v1.0 ne fournissait que trois points par dimension. Les paliers
suivants constituent des décisions fermes du pilotage :

1. DÉLAIS (d = delta de retard du projet en points = avancement temporel - physique) :
   - d <= 5       -> Score 100
   - 5 < d <= 15  -> Score 40
   - d > 15       -> Score 10

2. RAPPORTS (fenêtre des 7 derniers jours calendaires jusqu'à date_reference comprise) :
   - Jours attendus : jours OUVRÉS du calendrier d'entreprise, postérieurs ou
     égaux à premier_jour_rapport(projet).
   - Jours couverts : jours disposant d'un rapport SOUMIS ou APPROUVE non supprimé.
   - Taux = couverts / attendus * 100 (100 % si aucun jour attendu).
   - taux = 100        -> Score 100
   - 70 <= taux < 100  -> Score 40
   - taux < 70         -> Score 10

3. BLOCAGES (statuts OUVERT ou PRIS_EN_CHARGE, non supprimés) :
   - Aucun blocage ouvert                   -> Score 100
   - Seulement des blocages MINEUR          -> Score 40
   - Au moins un blocage MAJEUR ou CRITIQUE -> Score 10

4. INCIDENTS (lignes de saisie["incidents"] des rapports SOUMIS ou APPROUVE
   sur les 14 derniers jours calendaires) :
   - Gravités retenues : MINEUR, SIGNIFICATIF, GRAVE
   - Aucun incident       -> Score 100
   - Aucun incident GRAVE -> Score 40
   - Au moins un GRAVE    -> Score 10

5. INDICE DE SANTÉ (Formule 6) :
   - Somme pondérée : somme(score * ponderation / 100)
   - Pondérations lues dans settings.F3_PONDERATIONS_INDICE_SANTE
     (délais 40, rapports 25, blocages 20, incidents 15).
   - Règle d'arrondi : ROUND_HALF_UP (arrondi arithmétique standard, 0.5 supérieur),
     borné dans [0, 100].

6. BADGE OPÉRATIONNEL :
   - score >= settings.SANTE_SEUIL_VERT (80)    -> VERT
   - score >= settings.SANTE_SEUIL_ORANGE (50)  -> ORANGE
   - score < settings.SANTE_SEUIL_ORANGE (50)   -> ROUGE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import prefetch_related_objects
from django.utils import timezone

from apps.chantier.services.journal import premier_jour_rapport
from apps.core.enums import StatutBlocage, StatutProjet, StatutRapport
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.sante_calculs import (
    calculer_delta_projet,
    determiner_badge,
)

STATUTS_SANTE_FIGES = frozenset(
    {
        StatutProjet.SUSPENDU,
        StatutProjet.RECEPTIONNE,
        StatutProjet.TERMINE,
        StatutProjet.DESACTIVE,
        StatutProjet.RESILIE,
        StatutProjet.ARCHIVE,
    }
)

__all__ = [
    "STATUTS_SANTE_FIGES",
    "IndiceSante",
    "determiner_badge",
    "evaluer_indice_sante",
    "indice_sante",
    "score_blocages",
    "score_delais",
    "score_incidents",
    "score_rapports",
]


# ==============================================================================
# 1. FONCTIONS PURES DES SCORES PAR DIMENSION (PALIERS DU PILOTAGE)
# ==============================================================================


def score_delais(delta: float) -> int:
    """Score de la dimension Délais selon les paliers de pilotage.

    d = delta de retard du projet en points (avancement temporel - physique).
    Paliers :
    - d <= 5       -> 100
    - 5 < d <= 15  -> 40
    - d > 15       -> 10
    """
    if delta <= 5.0:
        return 100
    if delta <= 15.0:
        return 40
    return 10


def score_rapports(attendus: int, couverts: int) -> int:
    """Score de la dimension Rapports selon les paliers de pilotage.

    Taux = couverts / attendus * 100 (100 si aucun jour attendu).
    Paliers :
    - taux = 100        -> 100
    - 70 <= taux < 100  -> 40
    - taux < 70         -> 10
    """
    if attendus <= 0:
        return 100
    taux = (couverts / attendus) * 100.0
    if taux >= 100.0:
        return 100
    if taux >= 70.0:
        return 40
    return 10


def score_blocages(severites_ouvertes: list[str]) -> int:
    """Score de la dimension Blocages selon les paliers de pilotage.

    Sévérités des blocages actifs (statut OUVERT ou PRIS_EN_CHARGE non supprimés).
    Paliers :
    - aucun                                  -> 100
    - seulement des MINEUR                   -> 40
    - au moins un MAJEUR ou un CRITIQUE      -> 10
    """
    if not severites_ouvertes:
        return 100
    for sev in severites_ouvertes:
        if sev in {"MAJEUR", "CRITIQUE"}:
            return 10
    return 40


def score_incidents(gravites: list[str]) -> int:
    """Score de la dimension Incidents selon les paliers de pilotage.

    Lignes d'incidents des rapports SOUMIS ou APPROUVE des 14 derniers jours.
    Ne prend en compte que les gravités valides (MINEUR, SIGNIFICATIF, GRAVE).
    Paliers :
    - aucun incident        -> 100
    - aucun incident GRAVE  -> 40
    - au moins un GRAVE     -> 10
    """
    gravites_valides = [g for g in gravites if g in {"MINEUR", "SIGNIFICATIF", "GRAVE"}]
    if not gravites_valides:
        return 100
    if any(g == "GRAVE" for g in gravites_valides):
        return 10
    return 40


def indice_sante(
    s_delais: int,
    s_rapports: int,
    s_blocages: int,
    s_incidents: int,
) -> int:
    """Calcule l'indice de santé synthétique (Formule 6, SFD F3 §4.6).

    INDICE = arrondi entier de somme(score * ponderation / 100).
    Lit dynamiquement les pondérations dans settings.F3_PONDERATIONS_INDICE_SANTE.
    Règle d'arrondi : ROUND_HALF_UP (arrondi arithmétique standard, 0.5 vers le haut).
    """
    ponderations = settings.F3_PONDERATIONS_INDICE_SANTE
    p_delais = Decimal(str(ponderations["delais"]))
    p_rapports = Decimal(str(ponderations["rapports"]))
    p_blocages = Decimal(str(ponderations["blocages"]))
    p_incidents = Decimal(str(ponderations["incidents"]))

    somme = (
        Decimal(s_delais) * p_delais
        + Decimal(s_rapports) * p_rapports
        + Decimal(s_blocages) * p_blocages
        + Decimal(s_incidents) * p_incidents
    ) / Decimal("100")

    score_entier = int(somme.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(0, min(100, score_entier))


# ==============================================================================
# 2. DATACLASS DU RÉSULTAT SYNTHÉTIQUE
# ==============================================================================


@dataclass
class IndiceSante:
    """Résultat synthétique de l'évaluation de l'indice de santé d'un projet."""

    indice: int
    badge: str
    scores: dict[str, int]
    delta: float
    taux_rapports: float
    avertissements: list[str] = field(default_factory=list)


# ==============================================================================
# 3. FONCTION MAÎTRESSE EN BASE (ÉVALUATION D'UN PROJET)
# ==============================================================================


def evaluer_indice_sante(
    projet: Any,
    date_reference: date | None = None,
) -> IndiceSante:
    """Évalue l'indice de santé complet d'un projet en rassemblant ses données en base.

    Optimisations garanties :
    - Construit le calendrier de l'entreprise une seule fois.
    - Précharge les lots et activités via `prefetch_related_objects` pour éviter
      toute requête N+1 lors du calcul du delta d'avancement.
    - Récupère l'ensemble des rapports et incidents sur 14 jours en une seule requête SQL
      avec `select_related("journal")`, sans aucune requête par jour.
    - Analyse les blocages ouverts ou pris en charge en une requête SQL groupée.
    """
    date_ref = date_reference or timezone.localdate()

    # 1. Éviter toute requête par lot/activité lors du calcul de delta
    prefetch_related_objects([projet], "lots__activites")

    # 2. Construction unique du calendrier d'entreprise
    dates_projet = [
        d
        for d in [
            getattr(projet, "date_debut_prevue", None),
            getattr(projet, "date_fin_prevue", None),
            getattr(projet, "date_debut_reelle", None),
            getattr(projet, "date_fin_reelle", None),
            date_ref,
            date_ref - timedelta(days=14),
        ]
        if d is not None
    ]
    d_min = min(dates_projet) if dates_projet else date_ref
    d_max = max(dates_projet) if dates_projet else date_ref
    annee_min = min(d_min.year, date_ref.year - 1)
    annee_max = max(d_max.year, date_ref.year + 1)
    calendrier = calendrier_entreprise(date(annee_min, 1, 1), date(annee_max, 12, 31))

    avertissements: list[str] = []
    if getattr(calendrier, "est_incomplet", False):
        avertissements.append("JOURS_FERIES_INCOMPLETS")

    # 3. Dimension Délais : delta consolidé par calculer_delta_projet
    delta = float(calculer_delta_projet(projet, date_ref, calendrier))
    s_delais = score_delais(delta)

    # 4. Fenêtres temporelles pour rapports (7 jours) et incidents (14 jours)
    date_debut_14j = date_ref - timedelta(days=13)
    date_debut_7j = date_ref - timedelta(days=6)
    date_fin = date_ref

    # 5. Jours attendus pour les rapports (7 jours calendaires jusqu'à date_ref comprise)
    premier_jour = premier_jour_rapport(projet)

    dates_attendues: set[date] = set()
    courante = date_debut_7j
    while courante <= date_fin:
        if courante >= premier_jour and calendrier.est_ouvre(courante):
            dates_attendues.add(courante)
        courante += timedelta(days=1)
    attendus = len(dates_attendues)

    # 6. Requête SQL unique pour les rapports et incidents sur 14 jours (avec jointure journal)
    rapports_14j = list(
        projet.rapports_journaliers.filter(
            supprime_le__isnull=True,
            statut__in=[StatutRapport.SOUMIS, StatutRapport.APPROUVE],
            date_rapport__gte=date_debut_14j,
            date_rapport__lte=date_fin,
        ).select_related("journal")
    )

    # Jours couverts sur les 7 derniers jours (doivent avoir un rapport SOUMIS ou APPROUVE)
    dates_avec_rapport = {
        r.date_rapport
        for r in rapports_14j
        if date_debut_7j <= r.date_rapport <= date_fin
    }
    couverts = len(dates_attendues.intersection(dates_avec_rapport))

    taux_rapports = (
        100.0 if attendus <= 0 else float(round((couverts / attendus) * 100.0, 2))
    )

    s_rapports = score_rapports(attendus, couverts)

    # 7. Incidents des 14 derniers jours (saisie["incidents"])
    gravites_incidents: list[str] = []
    for r in rapports_14j:
        try:
            journal = r.journal
        except ObjectDoesNotExist:
            journal = None
        if journal and isinstance(journal.saisie, dict):
            incidents_list = journal.saisie.get("incidents", [])
            if isinstance(incidents_list, list):
                for inc in incidents_list:
                    if isinstance(inc, dict):
                        grav = inc.get("gravite")
                        if grav in {"MINEUR", "SIGNIFICATIF", "GRAVE"}:
                            gravites_incidents.append(grav)

    s_incidents = score_incidents(gravites_incidents)

    # 8. Dimension Blocages : blocages actifs non supprimés
    blocages_actifs = projet.blocages.filter(
        supprime_le__isnull=True,
        statut__in=[StatutBlocage.OUVERT, StatutBlocage.PRIS_EN_CHARGE],
    )
    severites_ouvertes = list(blocages_actifs.values_list("severite", flat=True))
    s_blocages = score_blocages(severites_ouvertes)

    # 9. Synthèse Formule 6 & Badge
    indice_final = indice_sante(s_delais, s_rapports, s_blocages, s_incidents)
    badge = determiner_badge(indice_final)

    scores = {
        "delais": s_delais,
        "rapports": s_rapports,
        "blocages": s_blocages,
        "incidents": s_incidents,
    }

    return IndiceSante(
        indice=indice_final,
        badge=badge,
        scores=scores,
        delta=delta,
        taux_rapports=taux_rapports,
        avertissements=avertissements,
    )
