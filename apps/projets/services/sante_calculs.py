"""Moteur de calcul pur pour l'Indice de Santé de Projet et ses pénalités.

Fonctions pures, déterministes et testables unitairement :
- Avancement physique (activité -> lot -> projet, pondération budgétaire avec repli uniforme).
- Avancement temporel (jours ouvrés écoulés vs baseline contractuelle v0).
- Delta de retard en points (retard_pts = temporel - physique).
- Pénalité Délais (retard clampé à 25 pts + malus des reports accordés du projet).
- Pénalité Blocages (gravité MINEUR/MAJEUR/CRITIQUE x multiplicateur d'ancienneté ouvrée).
- Pénalité Reporting (taux de présence de rapports valides sur 14 jours calendaires).
- Score synthétique (0-100), badges (VERT, ORANGE, ROUGE) et plancher de gravité.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.core.enums import BadgeSante, SeveriteBlocage, StatutActivite, StatutBlocage, StatutProjet, StatutRapport
from apps.projets.models.historique_date import TypeObjetHistorique
from apps.referentiels.models import JourFerie

logger = logging.getLogger(__name__)

__all__ = [
    "ResultatCalculSante",
    "calculer_avancement_physique_activite",
    "calculer_avancement_physique_lot",
    "calculer_avancement_physique_projet",
    "calculer_avancement_temporel_lot",
    "calculer_avancement_temporel_projet",
    "calculer_indice_sante_projet",
    "calculer_penalite_blocages",
    "calculer_penalite_delais",
    "calculer_penalite_reporting",
    "compter_jours_ouvres",
    "est_jour_ouvre",
    "obtenir_jours_feries_ci",
]


@dataclass
class ResultatCalculSante:
    """Résultat structuré complet du calcul d'indice de santé."""

    projet_id: Any
    etat: str  # "NON_DEMARRE", "ACTIF", "FIGE"
    score: int | None
    badge_brut: str | None
    badge_final: str | None
    plancher_applique: bool

    # Pénalités (détaillées)
    p_delais: float
    p_retard: float
    p_malus: float
    p_blocages: float
    p_reporting: float

    # Données d'avancement
    avancement_physique: float
    avancement_temporel: float
    retard_pts: float  # temporel - physique (positif = retard)
    mode_ponderation: str  # "BUDGET" ou "UNIFORME"

    # Détails de calcul
    nb_reports: int
    blocages_ouverts_par_severite: dict[str, int]
    taux_reporting: float
    jours_attendus: int
    jours_couverts: int

    avertissements: list[str] = field(default_factory=list)


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


def est_jour_ouvre(d: date, jours_feries: set[date]) -> bool:
    """Vérifie si un jour donné est ouvré (lundi à vendredi, hors férié)."""
    return d.weekday() < 5 and d not in jours_feries


def compter_jours_ouvres(debut: date, fin: date, jours_feries: set[date]) -> int:
    """Compte le nombre de jours ouvrés inclus entre debut et fin (bornes incluses)."""
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

    Règle CDC : Activite.quantite_realisee / Activite.quantite_prevue * 100.
    100 % si clôturée.
    Note contractuelle : La source est Activite.quantite_realisee directement,
    sans condition d'approbation préalable d'un rapport F2 (spécification V1).
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
    """Calcule l'avancement physique d'un lot : moyenne des activités actives pondérées par budget.

    Si une activité active n'a pas de budget initial > 0, repli à pondération uniforme.
    """
    activites = [
        a for a in lot.activites.all()
        if getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None
    ]
    if not activites:
        return float(lot.avancement or 0.0)

    budget_complet = all(
        a.budget_initial_montant is not None and a.budget_initial_montant > 0
        for a in activites
    )
    poids = [
        float(a.budget_initial_montant) if budget_complet else 1.0
        for a in activites
    ]
    total_poids = sum(poids)
    if total_poids <= 0:
        return 0.0

    avancements = [calculer_avancement_physique_activite(a) for a in activites]
    somme = sum(av * p for av, p in zip(avancements, poids, strict=True))
    return float(round(somme / total_poids, 2))


def obtenir_budget_effectif_lot(lot) -> float | None:
    """Retourne le budget initial du lot, ou à défaut la somme des budgets de ses activités actives."""
    b_lot = getattr(lot, "budget_initial_montant", None)
    if b_lot is not None and b_lot > 0:
        return float(b_lot)
    activites = [
        a for a in lot.activites.all()
        if getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None
    ]
    somme_act = sum(float(getattr(a, "budget_initial_montant", None) or 0) for a in activites)
    if somme_act > 0:
        return somme_act
    return None


def calculer_avancement_physique_projet(projet) -> tuple[float, str]:
    """Calcule l'avancement physique du projet : moyenne pondérée des lots actifs par leur budget effectif.

    Retourne (avancement_physique, mode_ponderation).
    Si un lot actif n'a pas de budget effectif > 0, repli à pondération uniforme.
    """
    lots = [
        lot for lot in projet.lots.all()
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]
    # Seuls les lots ayant une consistance (budget propre ou au moins une activité active) participent au calcul
    lots_pertinents = [
        lot for lot in lots
        if (getattr(lot, "budget_initial_montant", None) is not None and lot.budget_initial_montant > 0)
        or any(getattr(a, "est_actif", True) and getattr(a, "supprime_le", None) is None for a in lot.activites.all())
    ]
    if not lots_pertinents:
        return 0.0, "UNIFORME"

    budgets_lots = [obtenir_budget_effectif_lot(lot) for lot in lots_pertinents]
    budget_complet = all(b is not None and b > 0 for b in budgets_lots)
    poids = [b if budget_complet else 1.0 for b in budgets_lots]
    total_poids = sum(poids)
    if total_poids <= 0:
        return 0.0, "UNIFORME"

    avancements = [calculer_avancement_physique_lot(lot) for lot in lots_pertinents]
    somme = sum(av * p for av, p in zip(avancements, poids, strict=True))
    mode = "BUDGET" if budget_complet else "UNIFORME"
    return float(round(somme / total_poids, 2)), mode


def calculer_avancement_temporel_lot(
    lot,
    date_reference: date,
    jours_feries: set[date],
) -> float | None:
    """Calcule l'avancement temporel d'un lot : jours ouvrés écoulés / jours ouvrés totaux.

    Basé strictement sur la Baseline v0 contractuelle : lot.date_debut_baseline et lot.date_fin_baseline.
    Retourne None si les dates de baseline ne sont pas renseignées.
    """
    debut = getattr(lot, "date_debut_baseline", None)
    fin = getattr(lot, "date_fin_baseline", None)
    if not debut or not fin:
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
    jours_feries: set[date],
) -> tuple[float, list[str]]:
    """Calcule l'avancement temporel consolidé du projet (moyenne des lots pondérée par budget).

    Les lots sans baseline sont exclus du calcul temporel avec un avertissement.
    """
    avertissements = []
    lots = [
        lot for lot in projet.lots.all()
        if getattr(lot, "est_actif", True) and getattr(lot, "supprime_le", None) is None
    ]
    if not lots:
        return 0.0, avertissements

    lots_avec_temporel: list[tuple[Any, float]] = []
    for lot in lots:
        temp = calculer_avancement_temporel_lot(lot, date_reference, jours_feries)
        if temp is None:
            avertissements.append(f"LOT_SANS_BASELINE:{lot.code}")
        else:
            lots_avec_temporel.append((lot, temp))

    if not lots_avec_temporel:
        avertissements.append("AUCUN_LOT_AVEC_BASELINE")
        return 0.0, avertissements

    budgets_lots = [obtenir_budget_effectif_lot(lot) for lot, _ in lots_avec_temporel]
    budget_complet = all(b is not None and b > 0 for b in budgets_lots)
    poids = [b if budget_complet else 1.0 for b in budgets_lots]
    total_poids = sum(poids)
    if total_poids <= 0:
        return 0.0, avertissements

    somme = sum(temp * p for (_, temp), p in zip(lots_avec_temporel, poids, strict=True))
    return float(round(somme / total_poids, 2)), avertissements


# --------------------------------------------------------------------------
# Pénalité Délais (Plafond 40)
# --------------------------------------------------------------------------

def calculer_penalite_delais(
    retard_pts: float,
    nb_reports: int,
) -> tuple[float, float, float]:
    """Calcule la pénalité délais : P_delais = min(40, P_retard + P_malus).

    P_retard = 40 * clamp(retard_pts / DELTA_MAX_PTS, 0, 1) avec DELTA_MAX_PTS = 25.
    P_malus = nb_reports * MALUS_REPORT avec MALUS_REPORT = 2.
    Retourne (P_delais, P_retard, P_malus).
    """
    delta_max = getattr(settings, "SANTE_DELTA_MAX_PTS", 25)
    malus_unit = getattr(settings, "SANTE_MALUS_REPORT", 2)
    plafond = getattr(settings, "SANTE_PLAFOND_DELAIS", 40)

    ratio = max(0.0, min(1.0, retard_pts / delta_max)) if delta_max > 0 else 0.0
    p_retard = float(round(plafond * ratio, 2))
    p_malus = float(round(nb_reports * malus_unit, 2))
    p_delais = float(round(min(float(plafond), p_retard + p_malus), 2))
    return p_delais, p_retard, p_malus


# --------------------------------------------------------------------------
# Pénalité Blocages (Plafond 40)
# --------------------------------------------------------------------------

def multiplicateur_anciennete_blocage(jours_ouvres: int) -> float:
    """Retourne le coefficient multiplicateur selon les jours ouvrés d'ancienneté.

    Paliers :
    0 à 2 jours ouvrés -> x1.0
    3 à 7 jours ouvrés -> x1.5
    plus de 7 jours ouvrés -> x2.0
    """
    if jours_ouvres <= 2:
        return 1.0
    if jours_ouvres <= 7:
        return 1.5
    return 2.0


def calculer_penalite_blocages(
    blocages_ouverts: list[Any],
    date_reference: date,
    jours_feries: set[date],
) -> tuple[float, dict[str, int], bool]:
    """Calcule la pénalité blocages sur les blocages ouverts et pris en charge.

    P_blocages = min(40, somme(POIDS_BLOCAGE[sev] * multiplicateur_anciennete)).
    Retourne (P_blocages, decompte_severites, a_critique_ancien).
    a_critique_ancien vaut True si au moins un blocage CRITIQUE est ouvert depuis > 7 jours ouvrés.
    """
    poids_cfg = getattr(
        settings,
        "SANTE_POIDS_BLOCAGE",
        {"MINEUR": 2, "MAJEUR": 5, "CRITIQUE": 15},
    )
    plafond = getattr(settings, "SANTE_PLAFOND_BLOCAGES", 40)

    total_pts = 0.0
    decompte: dict[str, int] = {"MINEUR": 0, "MAJEUR": 0, "CRITIQUE": 0}
    a_critique_ancien = False

    for b in blocages_ouverts:
        sev = getattr(b, "severite", SeveriteBlocage.MINEUR)
        decompte[sev] = decompte.get(sev, 0) + 1
        poids = poids_cfg.get(sev, 2)

        ouvert_dt = getattr(b, "ouvert_le", None)
        if ouvert_dt:
            date_ouverture = timezone.localdate(ouvert_dt) if timezone.is_aware(ouvert_dt) else ouvert_dt.date()
        else:
            date_ouverture = date_reference

        # Ancienneté stricte en jours ouvrés écoulés après la date d'ouverture
        if date_reference > date_ouverture:
            anciennete_ouvres = compter_jours_ouvres(
                date_ouverture + timedelta(days=1), date_reference, jours_feries
            )
        else:
            anciennete_ouvres = 0

        mult = multiplicateur_anciennete_blocage(anciennete_ouvres)
        total_pts += poids * mult

        if sev == SeveriteBlocage.CRITIQUE and anciennete_ouvres > 7:
            a_critique_ancien = True

    p_blocages = float(round(min(float(plafond), total_pts), 2))
    return p_blocages, decompte, a_critique_ancien


# --------------------------------------------------------------------------
# Pénalité Reporting (Plafond 20)
# --------------------------------------------------------------------------

def est_dans_periode_arret(d: date, arrets: list[Any]) -> bool:
    """Vérifie si la date d tombe dans une période d'arrêt de chantier (bornes incluses)."""
    for a in arrets:
        if a.date_debut <= d:
            if a.date_fin is None or d <= a.date_fin:
                return True
    return False


def calculer_penalite_reporting(
    projet,
    date_reference: date,
    jours_feries: set[date],
    moment_actuel: datetime | None = None,
) -> tuple[float, float, int, int]:
    """Calcule la pénalité reporting sur la fenêtre des 14 derniers jours calendaires.

    - Fenêtre : [date_reference - 13 j, date_reference], bornée par date de début du projet.
    - Jours attendus : jours ouvrés, hors arrêts de chantier, et dont la tolérance de 48 h est échue.
    - Jours couverts : au moins un rapport SOUMIS ou APPROUVE soumis sous 48 h après la fin du jour.
    - P_reporting = 20 * (1 - taux) avec taux = couverts / attendus.
    Retourne (P_reporting, taux_reporting, jours_attendus, jours_couverts).
    """
    maintenant = moment_actuel or timezone.now()
    fuseau_nom = getattr(settings, "FUSEAU_AFFICHAGE", "Africa/Abidjan")
    fuseau = ZoneInfo(fuseau_nom)

    fenetre_nb = getattr(settings, "SANTE_FENETRE_REPORTING_JOURS", 14)
    tolerance_h = getattr(settings, "SANTE_TOLERANCE_SOUMISSION_HEURES", 48)
    plafond = getattr(settings, "SANTE_PLAFOND_REPORTING", 20)

    # 1. Bornes de la fenêtre calendaire
    date_debut_projet = getattr(projet, "date_debut_reelle", None) or getattr(projet, "date_debut_prevue", None)
    date_debut_fenetre = date_reference - timedelta(days=fenetre_nb - 1)
    if date_debut_projet and date_debut_projet > date_debut_fenetre:
        date_debut_fenetre = date_debut_projet

    if date_debut_fenetre > date_reference:
        return 0.0, 1.0, 0, 0

    dates_candidates: list[date] = []
    courante = date_debut_fenetre
    while courante <= date_reference:
        dates_candidates.append(courante)
        courante += timedelta(days=1)

    # 2. Arrêts de chantier du projet
    arrets = list(
        projet.arrets_chantier.filter(supprime_le__isnull=True)
    )

    # 3. Rapports journaliers SOUMIS ou APPROUVE du projet
    rapports_qs = projet.rapports_journaliers.filter(
        supprime_le__isnull=True,
        statut__in=[StatutRapport.SOUMIS, StatutRapport.APPROUVE],
        date_rapport__gte=date_debut_fenetre,
        date_rapport__lte=date_reference,
    )
    # Dictionnaire date_rapport -> liste des horodatages de soumission
    soumissions_par_date: dict[date, list[datetime]] = {}
    for r in rapports_qs:
        dt_soumis = r.soumis_le or r.cree_le
        if dt_soumis:
            soumissions_par_date.setdefault(r.date_rapport, []).append(dt_soumis)

    jours_attendus = 0
    jours_couverts = 0

    for d in dates_candidates:
        # Doit être un jour ouvré
        if not est_jour_ouvre(d, jours_feries):
            continue

        # Hors période d'arrêt de chantier
        if est_dans_periode_arret(d, arrets):
            continue

        # Échéance de tolérance : 48 h après la fin de la journée d (23h59:59 heure locale)
        fin_journee_locale = datetime.combine(d, time.max, tzinfo=fuseau)
        echeance_tolerance = fin_journee_locale + timedelta(hours=tolerance_h)

        # Si la tolérance de 48 h n'est pas encore écoulée, le jour n'est pas encore exigible
        if maintenant < echeance_tolerance:
            continue

        jours_attendus += 1

        # Vérification si un rapport a été soumis au plus tard à l'échéance de tolérance
        dates_soumises = soumissions_par_date.get(d, [])
        couvert = any(s <= echeance_tolerance for s in dates_soumises)
        if couvert:
            jours_couverts += 1

    if jours_attendus == 0:
        return 0.0, 1.0, 0, 0

    taux = float(round(jours_couverts / jours_attendus, 4))
    p_reporting = float(round(plafond * (1.0 - taux), 2))
    return p_reporting, taux, jours_attendus, jours_couverts


# --------------------------------------------------------------------------
# Fonction Maîtresse : Calcul Complet de l'Indice de Santé
# --------------------------------------------------------------------------

def calculer_indice_sante_projet(
    projet,
    date_reference: date | None = None,
    moment_actuel: datetime | None = None,
) -> ResultatCalculSante:
    """Calcule l'indice de santé complet d'un projet selon la spécification BTP.

    Fonction pure sans persistance en base.
    """
    date_ref = date_reference or timezone.localdate()
    maintenant = moment_actuel or timezone.now()
    avertissements: list[str] = []

    # 1. Vérification des états du projet (C2)
    statut = getattr(projet, "statut", StatutProjet.EN_COURS)

    # État NON_DEMARRE : EN_ATTENTE uniquement (C2)
    if statut == StatutProjet.EN_ATTENTE:
        return ResultatCalculSante(
            projet_id=projet.id,
            etat="NON_DEMARRE",
            score=None,
            badge_brut=None,
            badge_final=None,
            plancher_applique=False,
            p_delais=0.0,
            p_retard=0.0,
            p_malus=0.0,
            p_blocages=0.0,
            p_reporting=0.0,
            avancement_physique=0.0,
            avancement_temporel=0.0,
            retard_pts=0.0,
            mode_ponderation="UNIFORME",
            nb_reports=0,
            blocages_ouverts_par_severite={},
            taux_reporting=1.0,
            jours_attendus=0,
            jours_couverts=0,
            avertissements=["PROJET_NON_DEMARRE"],
        )

    # États FIGES : SUSPENDU, RECEPTIONNE, TERMINE, DESACTIVE, RESILIE, ARCHIVE
    # Le dernier indice doit être figé et conservé, sans recalcul
    if statut in {
        StatutProjet.SUSPENDU,
        StatutProjet.RECEPTIONNE,
        StatutProjet.TERMINE,
        StatutProjet.DESACTIVE,
        StatutProjet.RESILIE,
        StatutProjet.ARCHIVE,
    }:
        score_stocke = getattr(projet, "indice_sante", None)
        badge_stocke = getattr(projet, "badge_sante", None)
        return ResultatCalculSante(
            projet_id=projet.id,
            etat="FIGE",
            score=score_stocke,
            badge_brut=badge_stocke,
            badge_final=badge_stocke,
            plancher_applique=False,
            p_delais=0.0,
            p_retard=0.0,
            p_malus=0.0,
            p_blocages=0.0,
            p_reporting=0.0,
            avancement_physique=float(projet.avancement_reel or 0.0),
            avancement_temporel=float(projet.avancement_theorique or 0.0),
            retard_pts=float((projet.avancement_theorique or 0.0) - (projet.avancement_reel or 0.0)),
            mode_ponderation="FIGE",
            nb_reports=0,
            blocages_ouverts_par_severite={},
            taux_reporting=1.0,
            jours_attendus=0,
            jours_couverts=0,
            avertissements=[f"PROJET_FIGE_STATUT_{statut}"],
        )

    # 2. Récupération des jours fériés pour la fenêtre du projet
    annee_min = date_ref.year - 1
    annee_max = date_ref.year + 1
    jours_feries, est_incomplet = obtenir_jours_feries_ci(annee_min, annee_max)
    if est_incomplet:
        avertissements.append("JOURS_FERIES_INCOMPLETS")

    # 3. Avancements physique et temporel
    av_physique, mode_pond = calculer_avancement_physique_projet(projet)
    av_temporel, avert_temp = calculer_avancement_temporel_projet(projet, date_ref, jours_feries)
    avertissements.extend(avert_temp)

    # Retard en points (retard_pts = temporel - physique, positif = retard) (C4)
    retard_pts = float(round(av_temporel - av_physique, 2))

    # 4. Pénalité Délais (Section 4)
    # Nombre d'enregistrements HistoriqueDate du projet portant sur date_fin_prevue avec ecart_jours > 0
    nb_reports = projet.historique_dates.filter(
        supprime_le__isnull=True,
        type_objet=TypeObjetHistorique.PROJET,
        champ="date_fin_prevue",
        ecart_jours__gt=0,
    ).count()

    p_delais, p_retard, p_malus = calculer_penalite_delais(retard_pts, nb_reports)

    # 5. Pénalité Blocages (Section 5)
    blocages_actifs = list(
        projet.blocages.filter(
            supprime_le__isnull=True,
            statut__in=[StatutBlocage.OUVERT, StatutBlocage.PRIS_EN_CHARGE],
        )
    )
    p_blocages, decompte_sev, a_critique_ancien = calculer_penalite_blocages(
        blocages_actifs, date_ref, jours_feries
    )

    # 6. Pénalité Reporting (Section 6)
    p_reporting, taux_rep, attendus, couverts = calculer_penalite_reporting(
        projet, date_ref, jours_feries, moment_actuel=maintenant
    )

    # 7. Score synthétique brut et arrondi
    total_penalites = p_delais + p_blocages + p_reporting
    score_brut = max(0.0, 100.0 - total_penalites)

    # Arrondi à l'entier le plus proche (0.5 vers le haut : ROUND_HALF_UP)
    score_entier = int(
        Decimal(str(score_brut)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    score_entier = max(0, min(100, score_entier))

    # 8. Badge brut
    seuil_vert = getattr(settings, "SANTE_SEUIL_VERT", 80)
    seuil_orange = getattr(settings, "SANTE_SEUIL_ORANGE", 50)

    if score_entier >= seuil_vert:
        badge_brut = BadgeSante.VERT
    elif score_entier >= seuil_orange:
        badge_brut = BadgeSante.ORANGE
    else:
        badge_brut = BadgeSante.ROUGE

    # 9. Plancher de gravité (Section 8)
    # Si un blocage CRITIQUE est ouvert depuis > 7 jours ouvrés OU si retard_pts > 25 :
    # Le badge final est au minimum ORANGE (ne change pas le score numérique)
    plancher_requis = a_critique_ancien or (retard_pts > 25.0)
    plancher_applique = False
    badge_final = badge_brut

    if plancher_requis and badge_brut == BadgeSante.VERT:
        badge_final = BadgeSante.ORANGE
        plancher_applique = True

    return ResultatCalculSante(
        projet_id=projet.id,
        etat="ACTIF",
        score=score_entier,
        badge_brut=badge_brut,
        badge_final=badge_final,
        plancher_applique=plancher_applique,
        p_delais=p_delais,
        p_retard=p_retard,
        p_malus=p_malus,
        p_blocages=p_blocages,
        p_reporting=p_reporting,
        avancement_physique=av_physique,
        avancement_temporel=av_temporel,
        retard_pts=retard_pts,
        mode_ponderation=mode_pond,
        nb_reports=nb_reports,
        blocages_ouverts_par_severite=decompte_sev,
        taux_reporting=taux_rep,
        jours_attendus=attendus,
        jours_couverts=couverts,
        avertissements=avertissements,
    )
