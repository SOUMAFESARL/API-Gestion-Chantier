"""Tests unitaires pour le calcul de durée calendaire et ouvrée de projet (lot E1).

Tous les tests s'exécutent sans base de données (fonction pure et instance
Projet instanciée en mémoire sans persistance).
"""

from datetime import date

from apps.projets.models import Projet
from apps.projets.services.durees import decaler_mois, duree_calendaire


def test_duree_calendaire_annee_pleine():
    """duree_calendaire(2026-01-01, 2026-12-31) rend annees=1, mois=0, jours=0."""
    res = duree_calendaire(date(2026, 1, 1), date(2026, 12, 31))
    assert res == {"annees": 1, "mois": 0, "jours": 0}

    # Supporte également les chaînes ISO
    res_str = duree_calendaire("2026-01-01", "2026-12-31")
    assert res_str == {"annees": 1, "mois": 0, "jours": 0}


def test_duree_calendaire_fin_fevrier():
    """duree_calendaire(2026-01-31, 2026-02-28) rend annees=0, mois=1, jours=1 (règle frontend)."""
    res = duree_calendaire(date(2026, 1, 31), date(2026, 2, 28))
    assert res == {"annees": 0, "mois": 1, "jours": 1}

    res_str = duree_calendaire("2026-01-31", "2026-02-28")
    assert res_str == {"annees": 0, "mois": 1, "jours": 1}


def test_duree_calendaire_multi_annees():
    """duree_calendaire(2026-03-15, 2028-06-14) rend annees=2, mois=3, jours=0."""
    res = duree_calendaire(date(2026, 3, 15), date(2028, 6, 14))
    assert res == {"annees": 2, "mois": 3, "jours": 0}

    res_str = duree_calendaire("2026-03-15", "2028-06-14")
    assert res_str == {"annees": 2, "mois": 3, "jours": 0}


def test_duree_calendaire_meme_jour():
    """duree_calendaire(2026-10-19, 2026-10-19) rend annees=0, mois=0, jours=1."""
    res = duree_calendaire(date(2026, 10, 19), date(2026, 10, 19))
    assert res == {"annees": 0, "mois": 0, "jours": 1}

    res_str = duree_calendaire("2026-10-19", "2026-10-19")
    assert res_str == {"annees": 0, "mois": 0, "jours": 1}


def test_duree_calendaire_mois_et_jours():
    """duree_calendaire(2025-02-03, 2025-07-15) rend annees=0, mois=5, jours=13."""
    res = duree_calendaire(date(2025, 2, 3), date(2025, 7, 15))
    assert res == {"annees": 0, "mois": 5, "jours": 13}

    res_str = duree_calendaire("2025-02-03", "2025-07-15")
    assert res_str == {"annees": 0, "mois": 5, "jours": 13}


def test_duree_calendaire_date_manquante_ou_fin_anterieure():
    """Rend None si une date manque ou si la fin précède le début."""
    assert duree_calendaire(None, date(2026, 1, 1)) is None
    assert duree_calendaire(date(2026, 1, 1), None) is None
    assert duree_calendaire(None, None) is None
    assert duree_calendaire(date(2026, 1, 2), date(2026, 1, 1)) is None
    assert duree_calendaire("2026-01-02", "2026-01-01") is None


def test_projet_propriete_duree_calendaire():
    """Projet.duree_calendaire expose les quatre clés, jours_ouvres égal à duree_jours_ouvres."""
    projet = Projet(
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    res = projet.duree_calendaire
    assert res is not None
    assert set(res.keys()) == {"annees", "mois", "jours", "jours_ouvres"}
    assert res["annees"] == 1
    assert res["mois"] == 0
    assert res["jours"] == 0
    assert res["jours_ouvres"] == projet.duree_jours_ouvres
    assert isinstance(res["jours_ouvres"], int)


def test_projet_propriete_duree_calendaire_dates_manquantes_ou_incoherentes():
    """Projet.duree_calendaire rend None si dates manquantes ou incohérentes."""
    p_sans_debut = Projet(date_debut_prevue=None, date_fin_prevue=date(2026, 12, 31))
    assert p_sans_debut.duree_calendaire is None

    p_sans_fin = Projet(date_debut_prevue=date(2026, 1, 1), date_fin_prevue=None)
    assert p_sans_fin.duree_calendaire is None

    p_incoherent = Projet(date_debut_prevue=date(2026, 12, 31), date_fin_prevue=date(2026, 1, 1))
    assert p_incoherent.duree_calendaire is None


def test_decaler_mois():
    """Vérifie le décalage de mois avec ajustement au dernier jour du mois."""
    assert decaler_mois(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert decaler_mois(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert decaler_mois(date(2026, 8, 31), 1) == date(2026, 9, 30)
