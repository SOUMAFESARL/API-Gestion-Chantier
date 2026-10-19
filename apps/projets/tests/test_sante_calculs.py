"""Tests unitaires du moteur de calcul d'avancement et de l'indice SFD.

Couvre sante_calculs.py et indice_sante.py :
- Paliers fermes de pilotage pour les 4 dimensions SFD (délais, rapports, blocages, incidents).
- La Formule 6 de synthèse avec pondérations dynamiques et arrondi ROUND_HALF_UP.
- Les seuils d'attribution des badges opérationnels (VERT, ORANGE, ROUGE).
- L'avancement physique (activité, lot pondéré par quantite_prevue, projet par budget lot).
- L'avancement temporel (baseline v0, week-ends, jours fériés, bornes 0% et 100%).
- La détection d'années manquantes pour les jours fériés (avertissement JOURS_FERIES_INCOMPLETS).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.core.enums import (
    BadgeSante,
    StatutActivite,
)
from apps.projets.services.indice_sante import (
    indice_sante,
    score_blocages,
    score_delais,
    score_incidents,
    score_rapports,
)
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_activite,
    calculer_avancement_physique_lot,
    calculer_avancement_physique_projet,
    calculer_avancement_temporel_lot,
    compter_jours_ouvres,
    couverture_budget_projet,
    determiner_badge_brut,
    obtenir_jours_feries_ci,
)

# ==============================================================================
# 1. TESTS DES PALIERS FERMES DU PILOTAGE (SFD F3 §4.6)
# ==============================================================================

def test_paliers_score_delais():
    """Vérifie les paliers Délais : d <= 5 -> 100 ; 5 < d <= 15 -> 40 ; d > 15 -> 10."""
    # Retard nul ou inférieur/égal à 5 points
    assert score_delais(-10.0) == 100
    assert score_delais(0.0) == 100
    assert score_delais(5.0) == 100

    # Retard modéré entre 5 et 15 points
    assert score_delais(5.1) == 40
    assert score_delais(10.0) == 40
    assert score_delais(15.0) == 40

    # Retard important supérieur à 15 points
    assert score_delais(15.1) == 10
    assert score_delais(25.0) == 10
    assert score_delais(100.0) == 10


def test_paliers_score_rapports():
    """Vérifie les paliers Rapports :
    100% -> 100 ; 70% <= taux < 100% -> 40 ; taux < 70% -> 10.
    """
    # Aucun jour attendu -> 100
    assert score_rapports(0, 0) == 100
    assert score_rapports(-1, 0) == 100

    # Couverture totale (100 %)
    assert score_rapports(5, 5) == 100
    assert score_rapports(7, 7) == 100

    # Couverture partielle entre 70% et 100%
    assert score_rapports(10, 7) == 40   # 70 %
    assert score_rapports(10, 9) == 40   # 90 %
    assert score_rapports(7, 5) == 40    # 71.43 %

    # Couverture insuffisante (< 70 %)
    assert score_rapports(10, 6) == 10   # 60 %
    assert score_rapports(5, 0) == 10    # 0 %
    assert score_rapports(7, 4) == 10    # 57.14 %


def test_paliers_score_blocages():
    """Vérifie les paliers Blocages :
    aucun -> 100 ; seulement MINEUR -> 40 ; au moins un MAJEUR/CRITIQUE -> 10.
    """
    # Aucun blocage ouvert
    assert score_blocages([]) == 100

    # Uniquement des blocages MINEUR
    assert score_blocages(["MINEUR"]) == 40
    assert score_blocages(["MINEUR", "MINEUR", "MINEUR"]) == 40

    # Au moins un MAJEUR ou CRITIQUE
    assert score_blocages(["MAJEUR"]) == 10
    assert score_blocages(["CRITIQUE"]) == 10
    assert score_blocages(["MINEUR", "MAJEUR"]) == 10
    assert score_blocages(["MINEUR", "CRITIQUE"]) == 10
    assert score_blocages(["MAJEUR", "CRITIQUE"]) == 10


def test_paliers_score_incidents():
    """Vérifie les paliers Incidents :
    aucun -> 100 ; aucun GRAVE -> 40 ; au moins un GRAVE -> 10.
    """
    # Aucun incident ou que des gravités non retenues
    assert score_incidents([]) == 100
    assert score_incidents(["AUTRE_NON_RETENU"]) == 100

    # Uniquement MINEUR ou SIGNIFICATIF
    assert score_incidents(["MINEUR"]) == 40
    assert score_incidents(["SIGNIFICATIF"]) == 40
    assert score_incidents(["MINEUR", "SIGNIFICATIF"]) == 40

    # Au moins un GRAVE
    assert score_incidents(["GRAVE"]) == 10
    assert score_incidents(["MINEUR", "GRAVE"]) == 10
    assert score_incidents(["SIGNIFICATIF", "GRAVE"]) == 10


def test_indice_sante_synthese_formule_6():
    """Vérifie la Formule 6 : somme(score * pondération / 100) avec pondérations 40/25/20/15."""
    # 1. Nominal parfait : tous les scores à 100 -> Indice 100
    assert indice_sante(100, 100, 100, 100) == 100

    # 2. Cas critique total : tous les scores à 10 -> Indice 10
    assert indice_sante(10, 10, 10, 10) == 10

    # 3. Cas dégradé intermédiaire : tous les scores à 40 -> Indice 40
    assert indice_sante(40, 40, 40, 40) == 40

    # 4. Délais 100 (40 pts), Rapports 40 (10), Blocages 40 (8), Incidents 100 (15) -> 73
    assert indice_sante(100, 40, 40, 100) == 73

    # 5. Délais 40 (16 pts), Rapports 100 (25 pts), Blocages 40 (8 pts), Incidents 10 (1.5 pts)
    # Somme = 50.5 -> arrondi arithmétique ROUND_HALF_UP -> 51
    assert indice_sante(40, 100, 40, 10) == 51

    # 6. Délais 10 (4 pts), Rapports 10 (2.5 pts), Blocages 10 (2 pts), Incidents 100 (15 pts)
    # Somme = 23.5 -> arrondi ROUND_HALF_UP -> 24
    assert indice_sante(10, 10, 10, 100) == 24


def test_determiner_badge_brut_seuils():
    """Vérifie l'attribution du badge selon SANTE_SEUIL_VERT (80) et SANTE_SEUIL_ORANGE (50)."""
    assert determiner_badge_brut(100) == BadgeSante.VERT
    assert determiner_badge_brut(80) == BadgeSante.VERT
    assert determiner_badge_brut(79) == BadgeSante.ORANGE
    assert determiner_badge_brut(50) == BadgeSante.ORANGE
    assert determiner_badge_brut(49) == BadgeSante.ROUGE
    assert determiner_badge_brut(10) == BadgeSante.ROUGE


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


@pytest.mark.django_db
def test_obtenir_jours_feries_ci_incomplet():
    """Vérifie que si une année est absente de la table, est_incomplet=True et avertissement."""
    # Années 2030 à 2031 (qui ne sont pas en base)
    feries, est_incomplet = obtenir_jours_feries_ci(2030, 2031)
    assert est_incomplet is True
    assert isinstance(feries, set)



