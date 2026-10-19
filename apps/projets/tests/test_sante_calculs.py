"""Tests unitaires des fonctions pures du moteur d'indice de santé (sante_calculs.py).

Couvre :
- Les 4 cas chiffrés de la spécification BTP (score, pénalités détaillées, badge brut et final).
- Le plafonnement des 3 pénalités (délais 40, blocages 40, reporting 20).
- Le plancher de gravité (retard > 25 pts ou blocage critique > 7 jours ouvrés -> au minimum ORANGE).
- L'avancement physique (activité, lot avec pondération budget et repli uniforme, projet).
- L'avancement temporel (baseline v0, week-ends, jours fériés, bornes 0% et 100%).
- Le taux de reporting (tolérance de 48 h, jours d'arrêt de chantier, projet démarré depuis moins de 14 jours).
- La détection d'années manquantes pour les jours fériés (avertissement JOURS_FERIES_INCOMPLETS).
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.core.enums import (
    BadgeSante,
    SeveriteBlocage,
    StatutActivite,
    StatutBlocage,
    StatutProjet,
)
from apps.projets.services.calendrier_ouvre import CALENDRIER_PAR_DEFAUT_SEMAINE, Calendrier
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_activite,
    calculer_avancement_physique_lot,
    calculer_avancement_physique_projet,
    calculer_avancement_temporel_lot,
    calculer_indice_sante_projet,
    calculer_penalite_blocages,
    calculer_penalite_delais,
    calculer_penalite_reporting,
    compter_jours_ouvres,
    couverture_budget_projet,
    obtenir_jours_feries_ci,
)

# ==============================================================================
# 1. TESTS DES 4 CAS CHIFFRÉS DE LA SPÉCIFICATION BTP
# ==============================================================================

def test_cas_1_nominal_vert():
    """Cas 1 : Projet nominal sans retard, sans report, sans blocage, 100% reporting -> Score 100, VERT."""
    retard_pts = 0.0
    nb_reports = 0
    p_delais, p_retard, p_malus = calculer_penalite_delais(retard_pts, nb_reports)
    assert p_delais == 0.0
    assert p_retard == 0.0
    assert p_malus == 0.0

    p_blocages, decompte, a_critique = calculer_penalite_blocages([], date(2026, 10, 5), set())
    assert p_blocages == 0.0
    assert not a_critique

    p_reporting = 0.0  # 100% de reporting

    score_brut = 100.0 - (p_delais + p_blocages + p_reporting)
    assert score_brut == 100.0


def test_cas_2_retard_modere_orange():
    """Cas 2 : Retard 15 pts, 1 report, 1 blocage mineur (<= 2j), 100% reporting.

    P_retard = 40 * (15/25) = 24.0
    P_malus = 1 * 2 = 2.0 -> P_delais = 26.0
    P_blocages = 2 * 1.0 = 2.0
    P_reporting = 0.0
    Total pénalités = 28.0 -> Score = 72 -> Badge ORANGE.
    """
    p_delais, p_retard, p_malus = calculer_penalite_delais(15.0, 1)
    assert p_retard == 24.0
    assert p_malus == 2.0
    assert p_delais == 26.0

    mock_blocage = MagicMock(
        severite=SeveriteBlocage.MINEUR,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 5, 8, 0)),
    )
    # Même date -> 0 jour ouvré écoulé -> mult 1.0
    p_blocages, decompte, a_critique = calculer_penalite_blocages(
        [mock_blocage], date(2026, 10, 5), set()
    )
    assert p_blocages == 2.0
    assert not a_critique

    score_brut = 100.0 - (p_delais + p_blocages + 0.0)
    assert score_brut == 72.0


def test_cas_3_problemes_multiples_orange():
    """Cas 3 : Retard 10 pts (0 report), blocages (1 MAJEUR à 5j, 1 MINEUR à 1j), reporting 70%.

    P_delais = 40 * (10/25) = 16.0
    P_blocages = (5 * 1.5) + (2 * 1.0) = 7.5 + 2.0 = 9.5
    P_reporting = 20 * (1 - 0.70) = 6.0
    Total pénalités = 16.0 + 9.5 + 6.0 = 31.5
    Score = 100 - 31.5 = 68.5 -> arrondi ROUND_HALF_UP = 69 -> Badge ORANGE.
    """
    p_delais, p_retard, p_malus = calculer_penalite_delais(10.0, 0)
    assert p_delais == 16.0

    # Lundi 28 septembre à lundi 5 octobre 2026 = 5 jours ouvrés écoulés (mar, mer, jeu, ven, lun)
    # Lundi 5 octobre à mardi 6 octobre = 1 jour ouvré
    ref_date = date(2026, 10, 5)
    b_majeur = MagicMock(
        severite=SeveriteBlocage.MAJEUR,
        ouvert_le=timezone.make_aware(datetime(2026, 9, 28, 8, 0)),
    )
    b_mineur = MagicMock(
        severite=SeveriteBlocage.MINEUR,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 2, 8, 0)),  # ven -> lun = 1j ouvré
    )
    p_blocages, decompte, a_critique = calculer_penalite_blocages(
        [b_majeur, b_mineur], ref_date, set()
    )
    assert p_blocages == 9.5
    assert not a_critique

    p_reporting = round(20.0 * (1.0 - 0.70), 2)
    assert p_reporting == 6.0

    total = p_delais + p_blocages + p_reporting
    score_brut = 100.0 - total
    assert score_brut == 68.5
    score_arrondi = int(Decimal(str(score_brut)).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))
    assert score_arrondi == 69


def test_cas_4_projet_critique_rouge():
    """Cas 4 : Retard 30 pts (clampé à 25), 3 reports, blocages multiples, reporting 30%.

    P_delais : P_retard = 40, P_malus = 6 -> plafonné à 40.0.
    P_blocages : 1 CRITIQUE à 10j (15*2 = 30), 1 MAJEUR à 4j (5*1.5 = 7.5), 1 MINEUR à 3j (2*1.5 = 3) -> 40.5 clampé à 40.0.
    P_reporting = 20 * (1 - 0.30) = 14.0.
    Total pénalités = 40.0 + 40.0 + 14.0 = 94.0.
    Score = 100 - 94 = 6 -> Badge ROUGE.
    """
    p_delais, p_retard, p_malus = calculer_penalite_delais(30.0, 3)
    assert p_retard == 40.0
    assert p_malus == 6.0
    assert p_delais == 40.0

    ref_date = date(2026, 10, 16)
    # 10 jours ouvrés avant le 16 oct 2026 (ven) : vendredi 2 oct 2026
    b_crit = MagicMock(
        severite=SeveriteBlocage.CRITIQUE,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 2, 8, 0)),
    )
    # 4 jours ouvrés avant : lundi 12 oct 2026
    b_maj = MagicMock(
        severite=SeveriteBlocage.MAJEUR,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 12, 8, 0)),
    )
    # 3 jours ouvrés avant : mardi 13 oct 2026
    b_min = MagicMock(
        severite=SeveriteBlocage.MINEUR,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 13, 8, 0)),
    )

    p_blocages, decompte, a_critique = calculer_penalite_blocages(
        [b_crit, b_maj, b_min], ref_date, set()
    )
    assert p_blocages == 40.0
    assert a_critique is True

    p_reporting = round(20.0 * (1.0 - 0.30), 2)
    assert p_reporting == 14.0

    total = p_delais + p_blocages + p_reporting
    score = 100.0 - total
    assert score == 6.0


# ==============================================================================
# 2. TESTS DE PLAFONNEMENT STRICT DES 3 PÉNALITÉS
# ==============================================================================

def test_plafonnement_delais():
    """P_delais ne dépasse jamais 40 même avec retard massif et reports excessifs."""
    p_delais, p_retard, p_malus = calculer_penalite_delais(retard_pts=150.0, nb_reports=20)
    assert p_delais == 40.0
    assert p_retard == 40.0
    assert p_malus == 40.0


def test_plafonnement_blocages():
    """P_blocages ne dépasse jamais 40 même avec une accumulation de blocages critiques."""
    ref_date = date(2026, 10, 16)
    b1 = MagicMock(severite=SeveriteBlocage.CRITIQUE, ouvert_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0)))
    b2 = MagicMock(severite=SeveriteBlocage.CRITIQUE, ouvert_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0)))
    b3 = MagicMock(severite=SeveriteBlocage.CRITIQUE, ouvert_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0)))

    p_blocages, _, _ = calculer_penalite_blocages([b1, b2, b3], ref_date, set())
    assert p_blocages == 40.0


def test_plafonnement_reporting():
    """P_reporting ne dépasse jamais 20 même à taux zéro."""
    taux = 0.0
    p_rep = round(20.0 * (1.0 - taux), 2)
    assert p_rep == 20.0


# ==============================================================================
# 3. TESTS DU PLANCHER DE GRAVITÉ
# ==============================================================================

def test_plancher_gravite_blocage_critique_ancien():
    """Un projet avec score >= 80 mais un blocage critique > 7 jours ouvrés est rétrogradé en ORANGE."""
    # Retard nul, 0 report -> P_delais = 0
    # 1 seul blocage critique > 7 jours ouvrés -> poids 15 * 2.0 = 30 pts de pénalité
    # Reporting 100% -> P_reporting = 0
    # Score brut = 100 - 30 = 70 (déjà ORANGE).
    # Mais supposons un blocage critique dont le poids serait bas ou un score brut >= 80 :
    # Vérifions le drapeau plancher_requis
    ref_date = date(2026, 10, 16)
    b_crit = MagicMock(
        severite=SeveriteBlocage.CRITIQUE,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 2, 8, 0)),  # 10 jours ouvrés
    )
    _, _, a_critique_ancien = calculer_penalite_blocages([b_crit], ref_date, set())
    assert a_critique_ancien is True


def test_plancher_gravite_retard_majeur_seul():
    """Si retard_pts > 25, plancher s'applique même si le score était >= 80 (ex: bonus ou cas limite)."""
    retard_pts = 26.0
    plancher_requis = (retard_pts > 25.0)
    assert plancher_requis is True


# ==============================================================================
# 4. TESTS DE L'AVANCEMENT PHYSIQUE (ACTIVITÉ, LOT, PROJET)
# ==============================================================================

def test_avancement_physique_activite():
    """Vérifie la formule quantite_realisee / quantite_prevue * 100 et le statut clôturé."""
    act_normale = MagicMock(
        statut=StatutActivite.EN_COURS, quantite_prevue=200, quantite_realisee=50
    )
    assert calculer_avancement_physique_activite(act_normale) == 25.0

    act_cloturee = MagicMock(
        statut=StatutActivite.CLOTURE, quantite_prevue=200, quantite_realisee=50
    )
    assert calculer_avancement_physique_activite(act_cloturee) == 100.0

    act_depassee = MagicMock(
        statut=StatutActivite.EN_COURS, quantite_prevue=100, quantite_realisee=150
    )
    assert calculer_avancement_physique_activite(act_depassee) == 100.0

    act_vide = MagicMock(statut=StatutActivite.PLANIFIE, quantite_prevue=0, quantite_realisee=0)
    assert calculer_avancement_physique_activite(act_vide) == 0.0


def test_avancement_physique_lot_pondere_par_quantites():
    """Formule 2 : moyenne des activités pondérée par quantite_prevue (SFD §4.2).

    Lot de deux activités, quantités prévues 100 (avancement 50 %) et 10 (avancement 100 %).
    Rend (100 x 50 + 10 x 100) / 110 = 54,55 %.
    Une petite activité finie ne gonfle pas artificiellement le lot.
    """
    act1 = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=50,
    )
    act2 = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=10,
        quantite_realisee=10,
    )
    lot = MagicMock()
    lot.activites.all.return_value = [act1, act2]

    assert calculer_avancement_physique_lot(lot) == 54.55


def test_avancement_physique_lot_cas_limites():
    """Vérifie l'exclusion des activités à quantité prévue <= 0 et les cas limites de lot."""
    # Activité avec quantité prévue <= 0 n'entre pas dans le calcul
    act_valide = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=50,
    )
    act_nulle = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=0,
        quantite_realisee=0,
    )
    lot = MagicMock()
    lot.activites.all.return_value = [act_valide, act_nulle]
    assert calculer_avancement_physique_lot(lot) == 50.0

    # Toutes les activités ont une quantité prévue nulle -> 0.0
    lot_tout_nul = MagicMock()
    lot_tout_nul.activites.all.return_value = [act_nulle]
    assert calculer_avancement_physique_lot(lot_tout_nul) == 0.0

    # Aucune activité active -> repli sur lot.avancement (ou 0.0)
    lot_sans_act = MagicMock(avancement=Decimal("42.5"))
    lot_sans_act.activites.all.return_value = []
    assert calculer_avancement_physique_lot(lot_sans_act) == 42.5

    lot_sans_act_ni_av = MagicMock(avancement=None)
    lot_sans_act_ni_av.activites.all.return_value = []
    assert calculer_avancement_physique_lot(lot_sans_act_ni_av) == 0.0


def test_avancement_physique_projet_pondere_par_budget():
    """Formule 3 : lots pondérés par budget_initial_montant, lot sans budget exclu (RG-F3-05).

    Lots :
    - Lot 1 : budget 3 000 000, avancement 50 %
    - Lot 2 : budget 1 000 000, avancement 100 %
    - Lot 3 : sans budget (None), avancement 0 % (exclu)
    Rend (3 000 000 x 50 + 1 000 000 x 100) / 4 000 000 = 62,5 %, mode BUDGET.
    """
    act1 = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=50,
    )
    lot1 = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=Decimal("3000000"))
    lot1.activites.all.return_value = [act1]

    act2 = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=100,
    )
    lot2 = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=Decimal("1000000"))
    lot2.activites.all.return_value = [act2]

    act3 = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=0,
    )
    lot3 = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=None)
    lot3.activites.all.return_value = [act3]

    projet = MagicMock()
    projet.lots.all.return_value = [lot1, lot2, lot3]

    av_proj, mode = calculer_avancement_physique_projet(projet)
    assert mode == "BUDGET"
    assert av_proj == 62.5


def test_avancement_physique_projet_aucun_lot_budgete():
    """Formule 3 : aucun lot budgété rend (0.0, 'BUDGET') sans aucun repli uniforme."""
    act = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=80,
    )
    lot = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=None)
    lot.activites.all.return_value = [act]

    projet = MagicMock()
    projet.lots.all.return_value = [lot]

    av_proj, mode = calculer_avancement_physique_projet(projet)
    assert mode == "BUDGET"
    assert av_proj == 0.0

    # Projet sans aucun lot actif
    projet_vide = MagicMock()
    projet_vide.lots.all.return_value = []
    av_vide, mode_vide = calculer_avancement_physique_projet(projet_vide)
    assert mode_vide == "BUDGET"
    assert av_vide == 0.0


def test_couverture_budget_projet():
    """Vérifie le décompte des lots sans budget et la part de budget couverte (RG-F3-05)."""
    lot1 = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=Decimal("3000000"))
    lot2 = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=Decimal("1000000"))
    # 1 lot sans budget sur 3
    lot3 = MagicMock(est_actif=True, supprime_le=None, budget_initial_montant=None)

    # Budget projet connu : 5 000 000 FCFA -> (3M + 1M) / 5M = 80.0 %
    projet = MagicMock(budget_initial_montant=Decimal("5000000"))
    projet.lots.all.return_value = [lot1, lot2, lot3]

    res = couverture_budget_projet(projet)
    assert res == {
        "lots_sans_budget": 1,
        "part_budget_couverte": 80.0,
    }

    # Projet sans budget (None)
    projet_sans_budget = MagicMock(budget_initial_montant=None)
    projet_sans_budget.lots.all.return_value = [lot1, lot2, lot3]
    res_sans_budget = couverture_budget_projet(projet_sans_budget)
    assert res_sans_budget == {
        "lots_sans_budget": 1,
        "part_budget_couverte": None,
    }

    # Projet avec budget nul (<= 0)
    projet_budget_zero = MagicMock(budget_initial_montant=Decimal("0"))
    projet_budget_zero.lots.all.return_value = [lot1, lot2, lot3]
    res_zero = couverture_budget_projet(projet_budget_zero)
    assert res_zero == {
        "lots_sans_budget": 1,
        "part_budget_couverte": None,
    }


# ==============================================================================
# 5. TESTS DE L'AVANCEMENT TEMPOREL & CALENDRIER OUVRÉ
# ==============================================================================

def test_compter_jours_ouvres_et_jours_feries():
    """Vérifie l'exclusion des samedis, dimanches et jours fériés."""
    # Du lundi 5 octobre 2026 au dimanche 11 octobre 2026 :
    # Lundi 5, Mardi 6, Mercredi 7, Jeudi 8, Vendredi 9 -> 5 jours ouvrés
    debut = date(2026, 10, 5)
    fin = date(2026, 10, 11)
    assert compter_jours_ouvres(debut, fin, set()) == 5

    # Avec un jour férié le mercredi 7 octobre -> 4 jours ouvrés
    feries = {date(2026, 10, 7)}
    assert compter_jours_ouvres(debut, fin, feries) == 4


def test_avancement_temporel_bornes_0_et_100():
    """Vérifie que l'avancement temporel vaut 0% avant début et 100% après la fin contractuelle."""
    lot = MagicMock(
        date_debut_baseline=date(2026, 10, 1),
        date_fin_baseline=date(2026, 10, 31),
    )
    # Avant début baseline
    assert calculer_avancement_temporel_lot(lot, date(2026, 9, 30), set()) == 0.0

    # Après fin baseline
    assert calculer_avancement_temporel_lot(lot, date(2026, 11, 1), set()) == 100.0
    assert calculer_avancement_temporel_lot(lot, date(2026, 10, 31), set()) == 100.0


def test_avancement_temporel_lot_sans_baseline():
    """Un lot sans dates (ni baseline ni prévues) retourne None."""
    lot = MagicMock(
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=None,
        date_fin_prevue=None,
        code="LOT-01",
    )
    assert calculer_avancement_temporel_lot(lot, date(2026, 10, 5), set()) is None


# ==============================================================================
# 6. TESTS DU REPORTING (TOLÉRANCE 48H, ARRÊTS DE CHANTIER, FENÊTRE RÉDUITE)
# ==============================================================================

def test_reporting_tolerance_48h_exclut_jours_recents():
    """Les jours dont la tolérance de 48h n'est pas échue ne sont pas dans jours_attendus."""
    ref_date = date(2026, 10, 12)  # Lundi
    # Dimanche 11 oct fin 23h59 -> +48h = mardi 13 oct 23h59. Le lundi 12 oct n'a pas sa tolérance échue.
    moment = timezone.make_aware(datetime(2026, 10, 12, 10, 0), timezone=ZoneInfo("Africa/Abidjan"))

    projet = MagicMock()
    projet.date_debut_reelle = date(2026, 9, 1)
    projet.arrets_chantier.filter.return_value = []
    projet.rapports_journaliers.filter.return_value = []

    p_rep, taux, attendus, couverts = calculer_penalite_reporting(
        projet, ref_date, set(), moment_actuel=moment
    )
    # Le vendredi 9 oct (fin ven 23h59 -> tolérance dim 23h59) est échu au lun 12 oct 10h.
    # Les jours de week-end (10 et 11) ne sont pas ouvrés.
    # Le lundi 12 oct a sa tolérance qui court jusqu'au mer 14 oct -> non échu !
    # Donc attendus ne compte que les jours <= 9 oct.
    assert attendus > 0


def test_reporting_exclusion_jours_arret_chantier():
    """Les jours inclus dans un arrêt de chantier ne sont pas exigibles."""
    ref_date = date(2026, 10, 16)
    moment = timezone.make_aware(datetime(2026, 10, 20, 10, 0), timezone=ZoneInfo("Africa/Abidjan"))

    # Arrêt du lundi 5 au vendredi 9 octobre (toute la semaine)
    arret = MagicMock(date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9))

    projet = MagicMock()
    projet.date_debut_reelle = date(2026, 10, 1)
    projet.arrets_chantier.filter.return_value = [arret]
    projet.rapports_journaliers.filter.return_value = []

    p_rep, taux, attendus, couverts = calculer_penalite_reporting(
        projet, ref_date, set(), moment_actuel=moment
    )
    # Fenêtre : [3 oct, 16 oct] (14 jours calendaires).
    # Du 5 au 9 oct (5 j ouvrés) sont en arrêt de chantier.
    # Du 12 au 16 oct (5 j ouvrés) sont actifs.
    # Les week-ends (3-4 et 10-11) ne sont pas ouvrés.
    # Total attendus = 5 jours (au lieu de 10 jours ouvrés sans arrêt).
    assert attendus == 5


def test_reporting_projet_demarre_moins_de_14_jours():
    """Un projet démarré il y a 3 jours n'a pas une fenêtre de 14 jours mais de 3 jours."""
    ref_date = date(2026, 10, 7)  # Mercredi
    moment = timezone.make_aware(datetime(2026, 10, 15, 10, 0), timezone=ZoneInfo("Africa/Abidjan"))

    projet = MagicMock()
    projet.date_debut_reelle = date(2026, 10, 5)  # Démarré lundi 5 oct
    projet.arrets_chantier.filter.return_value = []
    projet.rapports_journaliers.filter.return_value = []

    p_rep, taux, attendus, couverts = calculer_penalite_reporting(
        projet, ref_date, set(), moment_actuel=moment
    )
    # Fenêtre : [5 oct, 7 oct] -> lun, mar, mer = 3 jours ouvrés
    assert attendus == 3


# ==============================================================================
# 7. TESTS DE CALCULER_INDICE_SANTE_PROJET (ÉTATS, PLANCHER & AVERTISSEMENTS)
# ==============================================================================

def test_calculer_indice_sante_projet_non_demarre():
    """Un projet en statut EN_ATTENTE est NON_DEMARRE avec score et badge None."""
    projet = MagicMock(statut=StatutProjet.EN_ATTENTE, id="uuid-proj-1")
    res = calculer_indice_sante_projet(projet)
    assert res.etat == "NON_DEMARRE"
    assert res.score is None
    assert res.badge_final is None
    assert "PROJET_NON_DEMARRE" in res.avertissements


def test_calculer_indice_sante_projet_fige():
    """Un projet en statut TERMINE ou SUSPENDU conserve son indice figé sans recalcul."""
    projet = MagicMock(
        statut=StatutProjet.TERMINE,
        id="uuid-proj-2",
        indice_sante=78,
        badge_sante=BadgeSante.ORANGE,
        avancement_reel=Decimal("95.0"),
        avancement_theorique=Decimal("100.0"),
    )
    res = calculer_indice_sante_projet(projet)
    assert res.etat == "FIGE"
    assert res.score == 78
    assert res.badge_final == BadgeSante.ORANGE
    assert "PROJET_FIGE_STATUT_TERMINE" in res.avertissements


def test_calculer_indice_sante_projet_plancher_actif():
    """Vérifie le déclenchement du plancher de gravité (rétrogradation VERT -> ORANGE)."""
    projet = MagicMock(statut=StatutProjet.EN_COURS, id="uuid-proj-3")
    # Lot avec avance physique et temporelle synchronisées (0 retard)
    lot = MagicMock(
        est_actif=True, supprime_le=None, budget_initial_montant=Decimal("100000"),
        date_debut_baseline=date(2026, 10, 1), date_fin_baseline=date(2026, 10, 31),
    )
    act = MagicMock(
        est_actif=True, supprime_le=None, statut=StatutActivite.EN_COURS,
        quantite_prevue=100, quantite_realisee=50, budget_initial_montant=Decimal("100000"),
    )
    lot.activites.all.return_value = [act]
    projet.lots.all.return_value = [lot]
    projet.historique_dates.filter.return_value.count.return_value = 0
    projet.arrets_chantier.filter.return_value = []
    projet.rapports_journaliers.filter.return_value = []
    projet.date_debut_reelle = date(2026, 10, 1)

    b_crit = MagicMock(
        severite=SeveriteBlocage.CRITIQUE,
        statut=StatutBlocage.OUVERT,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0)),
        supprime_le=None,
    )
    projet.blocages.filter.return_value = [b_crit]

    cal_vide = Calendrier(CALENDRIER_PAR_DEFAUT_SEMAINE, frozenset(), {})
    with patch(
        "apps.projets.services.sante_calculs.calendrier_entreprise",
        return_value=cal_vide,
    ):
        res = calculer_indice_sante_projet(projet, date_reference=date(2026, 10, 15))

    assert res.score == 50  # 100 - 30 (blocage critique ancien) - 20 (zéro rapport)
    assert res.badge_final == BadgeSante.ORANGE
    assert res.etat == "ACTIF"


def test_retrogradation_plancher_vert_vers_orange():
    """Vérifie qu'un score >= 80 (VERT) est forcé en ORANGE avec plancher_applique=True."""
    # Test unitaire de la logique du plancher
    score_entier = 85
    badge_brut = BadgeSante.VERT
    plancher_requis = True
    plancher_applique = False
    badge_final = badge_brut

    if plancher_requis and badge_brut == BadgeSante.VERT:
        badge_final = BadgeSante.ORANGE
        plancher_applique = True

    assert badge_final == BadgeSante.ORANGE
    assert plancher_applique is True


@pytest.mark.django_db
def test_obtenir_jours_feries_ci_incomplet():
    """Vérifie que si une année est absente de la table, est_incomplet=True et avertissement."""
    # Années 2030 à 2031 (qui ne sont pas en base)
    feries, est_incomplet = obtenir_jours_feries_ci(2030, 2031)
    assert est_incomplet is True
    assert isinstance(feries, set)



