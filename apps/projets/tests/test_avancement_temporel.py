"""Tests unitaires de l'avancement temporel (Formule 4), du delta (Formule 5)
et du calendrier d'entreprise.

SFD F3 §4.4, §4.5 & Erratum v1.0.1 (E-1 et E-4).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.projets.models.calendrier import ExceptionCalendrier, SemaineType
from apps.projets.services.calendrier_ouvre import (
    CALENDRIER_PAR_DEFAUT_SEMAINE,
    Calendrier,
    calendrier_entreprise,
)
from apps.projets.services.sante_calculs import (
    calculer_avancement_temporel_lot,
    calculer_avancement_temporel_projet,
    calculer_delta_lot,
    calculer_delta_projet,
    compter_jours_ouvres,
)

# ==============================================================================
# 1. TEST L-01 DE L'ERRATUM (SANS BASE DE DONNÉES)
# ==============================================================================

def test_l01_avancement_temporel_erratum():
    """Test L-01 de l'erratum F3 v1.0.1 (E-1), sans base de données.

    Période : baseline 2025-02-03 -> 2025-07-15.
    Date de consultation : 2025-05-28.
    Jours fériés : {2025-03-27, 2025-03-30, 2025-04-21, 2025-05-01, 2025-05-29,
    2025-06-06, 2025-06-09}.
    Attendu : 111 jours ouvrés totaux, 80 jours ouvrés écoulés, 72.07 % d'avancement temporel.
    Vérifié d'abord avec l'ensemble de dates, puis avec un Calendrier équivalent.
    """
    debut = date(2025, 2, 3)
    fin = date(2025, 7, 15)
    date_ref = date(2025, 5, 28)
    feries_set = {
        date(2025, 3, 27),
        date(2025, 3, 30),
        date(2025, 4, 21),
        date(2025, 5, 1),
        date(2025, 5, 29),
        date(2025, 6, 6),
        date(2025, 6, 9),
    }

    lot = MagicMock(
        date_debut_baseline=debut,
        date_fin_baseline=fin,
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    # 1. Vérification avec l'ensemble de dates
    total_ouvres_set = compter_jours_ouvres(debut, fin, feries_set)
    ecoules_ouvres_set = compter_jours_ouvres(debut, date_ref, feries_set)
    temporel_set = calculer_avancement_temporel_lot(lot, date_ref, feries_set)

    assert total_ouvres_set == 111
    assert ecoules_ouvres_set == 80
    assert temporel_set == 72.07

    # 2. Vérification avec un Calendrier équivalent
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(feries_set),
        exceptions={},
    )
    total_ouvres_cal = compter_jours_ouvres(debut, fin, cal)
    ecoules_ouvres_cal = compter_jours_ouvres(debut, date_ref, cal)
    temporel_cal = calculer_avancement_temporel_lot(lot, date_ref, cal)

    assert total_ouvres_cal == 111
    assert ecoules_ouvres_cal == 80
    assert temporel_cal == 72.07


# ==============================================================================
# 2. TEST DE CALENDRIER.EST_OUVRE (HIÉRARCHIE DES 3 COUCHES)
# ==============================================================================

def test_calendrier_est_ouvre_trois_couches():
    """Vérifie la hiérarchie des 3 couches du Calendrier.

    1. Exception de l'entreprise (ouvré ou non ouvré) l'emporte sur tout.
    2. Férié national l'emporte sur la semaine type.
    3. Semaine type par défaut.
    """
    # Samedi travaillé par la semaine type (samedi = 5)
    semaine_avec_samedi = frozenset({0, 1, 2, 3, 4, 5})
    cal_samedi = Calendrier(
        jours_semaine=semaine_avec_samedi,
        feries=frozenset(),
        exceptions={},
    )
    samedi = date(2025, 2, 8)
    assert cal_samedi.est_ouvre(samedi) is True

    # Férié rendu ouvré par une exception d'entreprise
    fete_travail = date(2025, 5, 1)  # 1er mai
    cal_ferie_ouvre = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset({fete_travail}),
        exceptions={fete_travail: True},
    )
    assert cal_ferie_ouvre.est_ouvre(fete_travail) is True

    # Mardi fermé par une exception d'entreprise
    mardi = date(2025, 2, 4)
    cal_mardi_ferme = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={mardi: False},
    )
    assert cal_mardi_ferme.est_ouvre(mardi) is False

    # Férié standard sans exception -> non ouvré
    ascension = date(2025, 5, 29)
    cal_standard = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset({ascension}),
        exceptions={},
    )
    assert cal_standard.est_ouvre(ascension) is False


# ==============================================================================
# 3. FORMULE 4 : REPLI SUR LES DATES PRÉVUES & DATES MANQUANTES
# ==============================================================================

def test_avancement_temporel_lot_repli_dates_prevues():
    """Formule 4 : repli sur les dates prévues si la baseline n'est pas complète."""
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )

    # 1. Baseline complète : prime sur les dates prévues
    lot_baseline = MagicMock(
        date_debut_baseline=date(2025, 2, 3),
        date_fin_baseline=date(2025, 7, 15),
        date_debut_prevue=date(2025, 1, 1),
        date_fin_prevue=date(2025, 12, 31),
    )
    # 83 / 117 = 70.94 %
    assert calculer_avancement_temporel_lot(lot_baseline, date(2025, 5, 28), cal) == 70.94

    # 2. Absence totale de baseline : repli sur dates prévues
    lot_sans_base = MagicMock(
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=date(2025, 2, 3),
        date_fin_prevue=date(2025, 7, 15),
    )
    assert calculer_avancement_temporel_lot(lot_sans_base, date(2025, 5, 28), cal) == 70.94

    # 3. Baseline partielle (date_debut seule) : repli sur dates prévues
    lot_base_partielle_1 = MagicMock(
        date_debut_baseline=date(2025, 2, 3),
        date_fin_baseline=None,
        date_debut_prevue=date(2025, 2, 3),
        date_fin_prevue=date(2025, 7, 15),
    )
    assert calculer_avancement_temporel_lot(lot_base_partielle_1, date(2025, 5, 28), cal) == 70.94

    # 4. Baseline partielle (date_fin seule) : repli sur dates prévues
    lot_base_partielle_2 = MagicMock(
        date_debut_baseline=None,
        date_fin_baseline=date(2025, 7, 15),
        date_debut_prevue=date(2025, 2, 3),
        date_fin_prevue=date(2025, 7, 15),
    )
    assert calculer_avancement_temporel_lot(lot_base_partielle_2, date(2025, 5, 28), cal) == 70.94


def test_avancement_temporel_lot_none_sans_dates():
    """Formule 4 : rend None si ni la baseline ni les prévues ne forment une paire complète."""
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )

    # Aucune date
    lot_vide = MagicMock(
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    assert calculer_avancement_temporel_lot(lot_vide, date(2025, 5, 28), cal) is None

    # Prévue partielle sans baseline
    lot_prev_partiel = MagicMock(
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=date(2025, 2, 3),
        date_fin_prevue=None,
    )
    assert calculer_avancement_temporel_lot(lot_prev_partiel, date(2025, 5, 28), cal) is None


# ==============================================================================
# 4. FORMULE 4 : BORNES TEMPORELLES 0% ET 100%
# ==============================================================================

def test_avancement_temporel_lot_bornes_0_et_100():
    """Formule 4 : 0.0 % avant le début contractuel, 100.0 % à la fin ou après."""
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )
    lot = MagicMock(
        date_debut_baseline=date(2025, 2, 3),
        date_fin_baseline=date(2025, 7, 15),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    # Avant début contractuel
    assert calculer_avancement_temporel_lot(lot, date(2025, 2, 2), cal) == 0.0

    # Au jour exact de fin contractuelle
    assert calculer_avancement_temporel_lot(lot, date(2025, 7, 15), cal) == 100.0

    # Après la fin contractuelle
    assert calculer_avancement_temporel_lot(lot, date(2025, 7, 16), cal) == 100.0
    assert calculer_avancement_temporel_lot(lot, date(2026, 1, 1), cal) == 100.0


# ==============================================================================
# 5. FORMULE 5 : SIGNE DU DELTA (LOT ET PROJET)
# ==============================================================================

def test_calculer_delta_signe_retard():
    """Formule 5 : delta = temporel - physique (arrondi à 2 décimales, positif = retard)."""
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )

    # 1. Lot en retard : temporel 70.94 %, physique 50.0 % -> delta = +20.94 pts
    act_retard = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut="EN_COURS",
        quantite_prevue=100,
        quantite_realisee=50,
    )
    lot_retard = MagicMock(
        code="L01",
        est_actif=True,
        supprime_le=None,
        date_debut_baseline=date(2025, 2, 3),
        date_fin_baseline=date(2025, 7, 15),
        date_debut_prevue=None,
        date_fin_prevue=None,
        budget_initial_montant=Decimal("1000000"),
    )
    lot_retard.activites.all.return_value = [act_retard]
    delta_retard = calculer_delta_lot(lot_retard, date(2025, 5, 28), cal)
    assert delta_retard == 20.94  # positif = retard

    # 2. Lot en avance : temporel 70.94 %, physique 90.0 % -> delta = -19.06 pts
    act_avance = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut="EN_COURS",
        quantite_prevue=100,
        quantite_realisee=90,
    )
    lot_avance = MagicMock(
        code="L02",
        est_actif=True,
        supprime_le=None,
        date_debut_baseline=date(2025, 2, 3),
        date_fin_baseline=date(2025, 7, 15),
        date_debut_prevue=None,
        date_fin_prevue=None,
        budget_initial_montant=Decimal("1000000"),
    )
    lot_avance.activites.all.return_value = [act_avance]
    delta_avance = calculer_delta_lot(lot_avance, date(2025, 5, 28), cal)
    assert delta_avance == -19.06  # négatif = avance

    # 3. Lot synchrone : temporel 70.94 %, physique 70.94 % -> delta = 0.0 pts
    act_synchro = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut="EN_COURS",
        quantite_prevue=10000,
        quantite_realisee=7094,
    )
    lot_synchro = MagicMock(
        code="L03",
        est_actif=True,
        supprime_le=None,
        date_debut_baseline=date(2025, 2, 3),
        date_fin_baseline=date(2025, 7, 15),
        date_debut_prevue=None,
        date_fin_prevue=None,
        budget_initial_montant=Decimal("1000000"),
    )
    lot_synchro.activites.all.return_value = [act_synchro]
    assert calculer_delta_lot(lot_synchro, date(2025, 5, 28), cal) == 0.0

    # 4. Lot sans dates -> None
    lot_sans_dates = MagicMock(
        code="L04",
        est_actif=True,
        supprime_le=None,
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    assert calculer_delta_lot(lot_sans_dates, date(2025, 5, 28), cal) is None

    # 5. Delta projet
    projet = MagicMock()
    projet.lots.all.return_value = [lot_retard]
    delta_projet = calculer_delta_projet(projet, date(2025, 5, 28), cal)
    assert delta_projet == 20.94

    projet_avance = MagicMock()
    projet_avance.lots.all.return_value = [lot_avance]
    assert calculer_delta_projet(projet_avance, date(2025, 5, 28), cal) == -19.06

    projet_synchro = MagicMock()
    projet_synchro.lots.all.return_value = [lot_synchro]
    assert calculer_delta_projet(projet_synchro, date(2025, 5, 28), cal) == 0.0


# ==============================================================================
# 6. FORMULE 4 : PONDÉRATION PAR BUDGET DU TEMPOREL PROJET
# ==============================================================================

def test_avancement_temporel_projet_ponderation_budget():
    """Formule 4 consolidée : moyenne pondérée par budget_initial_montant (> 0).

    Exclut les lots sans dates (avec avertissement LOT_SANS_DATES:<code>)
    et les lots sans budget (> 0). Aucun repli uniforme.
    """
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )

    # Lot 1 : budget 3 000 000, du 01/01 au 31/01 -> au 31/01 = 100.0 %
    lot1 = MagicMock(
        code="L01",
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("3000000"),
        date_debut_baseline=date(2025, 1, 1),
        date_fin_baseline=date(2025, 1, 31),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    # Lot 2 : budget 1 000 000, du 01/02 au 28/02 -> au 31/01 = 0.0 %
    lot2 = MagicMock(
        code="L02",
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("1000000"),
        date_debut_baseline=date(2025, 2, 1),
        date_fin_baseline=date(2025, 2, 28),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    # Lot 3 : sans dates contractuelles -> exclu du calcul + avertissement
    lot3 = MagicMock(
        code="L03",
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("2000000"),
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    # Lot 4 : avec dates, mais sans budget (None) -> exclu du calcul
    lot4 = MagicMock(
        code="L04",
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=None,
        date_debut_baseline=date(2025, 1, 1),
        date_fin_baseline=date(2025, 1, 31),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    # Lot 5 : supprimé logiquement -> exclu du calcul
    lot5 = MagicMock(
        code="L05",
        est_actif=True,
        supprime_le=date(2025, 1, 10),
        budget_initial_montant=Decimal("5000000"),
        date_debut_baseline=date(2025, 1, 1),
        date_fin_baseline=date(2025, 1, 31),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    projet = MagicMock()
    projet.lots.all.return_value = [lot1, lot2, lot3, lot4, lot5]

    av, avertissements = calculer_avancement_temporel_projet(projet, date(2025, 1, 31), cal)

    # Poids retenus : lot1 (3M, 100%) + lot2 (1M, 0%) = 4M
    # Moyenne = (3 000 000 * 100 + 1 000 000 * 0) / 4 000 000 = 75.0 %
    assert av == 75.0
    assert "LOT_SANS_DATES:L03" in avertissements
    assert len([a for a in avertissements if a.startswith("LOT_SANS_DATES:")]) == 1


def test_avancement_temporel_projet_aucun_lot_retenu():
    """Formule 4 consolidée : renvoie 0.0 si aucun lot n'a à la fois dates et budget."""
    cal = Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )
    projet_vide = MagicMock()
    projet_vide.lots.all.return_value = []
    av, avert = calculer_avancement_temporel_projet(projet_vide, date(2025, 1, 31), cal)
    assert av == 0.0
    assert avert == []


# ==============================================================================
# 7. TESTS EN BASE DE DONNÉES DE CALENDRIER_ENTREPRISE
# ==============================================================================

@pytest.mark.django_db
def test_calendrier_entreprise_en_base(schema_demo):
    """Vérifie la construction du calendrier d'entreprise depuis la base de données.

    - La semaine type personnalisée est prise en compte.
    - Les exceptions actives de l'entreprise sont prises en compte.
    - Une exception supprimée logiquement n'est pas prise en compte.
    """
    # 1. Semaine type : ajout du samedi ouvré (samedi = 5)
    semaine = SemaineType.courante()
    semaine.samedi = True
    semaine.save()

    # 2. Exceptions de l'entreprise :
    # a) Un jour ouvré rendu chômé (vendredi pont)
    date_pont = date(2025, 5, 2)
    ExceptionCalendrier.objects.create(
        date=date_pont,
        ouvre=False,
        motif="Pont de la Fête du Travail",
    )

    # b) Un dimanche chômé rendu ouvré (travaux exceptionnels)
    date_dimanche = date(2025, 5, 4)
    ExceptionCalendrier.objects.create(
        date=date_dimanche,
        ouvre=True,
        motif="Coulage de dalle exceptionnel",
    )

    # c) Une exception supprimée logiquement
    date_suppr = date(2025, 5, 5)
    ExceptionCalendrier.objects.create(
        date=date_suppr,
        ouvre=False,
        motif="Exception annulée",
        supprime_le=timezone.now(),
    )

    cal = calendrier_entreprise(date(2025, 5, 1), date(2025, 5, 31))

    # Semaine type : samedi ouvré
    assert 5 in cal.jours_semaine
    samedi_test = date(2025, 5, 3)
    assert cal.est_ouvre(samedi_test) is True

    # Exception active non ouvrée (vendredi fermé)
    assert date_pont in cal.exceptions
    assert cal.exceptions[date_pont] is False
    assert cal.est_ouvre(date_pont) is False

    # Exception active ouvrée (dimanche travaillé)
    assert date_dimanche in cal.exceptions
    assert cal.exceptions[date_dimanche] is True
    assert cal.est_ouvre(date_dimanche) is True

    # Exception supprimée non prise en compte
    assert date_suppr not in cal.exceptions
    # Le 2025-05-05 est un lundi -> reste ouvré selon la semaine type
    assert cal.est_ouvre(date_suppr) is True
