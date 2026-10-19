"""Tests des fondations F3 (SFD F3 §4.6, §5.4, §8.1).

Vérifie sans base de données :
- Les constantes de configuration de l'indice de santé et des seuils F3.
- La présence et la configuration par défaut du champ f3_sync_done sur RapportJournalier.
"""

from django.conf import settings
from django.db import models

from apps.chantier.models.rapport_journalier import RapportJournalier


def test_f3_ponderations_indice_sante():
    """La somme des pondérations de l'indice de santé F3 vaut 100."""
    ponderations = settings.F3_PONDERATIONS_INDICE_SANTE
    assert set(ponderations.keys()) == {"delais", "rapports", "blocages", "incidents"}
    assert sum(ponderations.values()) == 100
    assert ponderations["delais"] == 40
    assert ponderations["rapports"] == 25
    assert ponderations["blocages"] == 20
    assert ponderations["incidents"] == 15


def test_f3_seuils_retard_pts():
    """Les seuils de retard F3 sont strictement croissants."""
    seuils = settings.F3_SEUILS_RETARD_PTS
    assert seuils["MODERE"] < seuils["ELEVE"] < seuils["CRITIQUE"]
    assert seuils == {"MODERE": 5, "ELEVE": 15, "CRITIQUE": 25}


def test_f3_seuil_indice_sante_critique():
    """Le seuil d'alerte critique sur l'indice de santé vaut 40."""
    assert settings.F3_SEUIL_INDICE_SANTE_CRITIQUE == 40


def test_rapport_journalier_f3_sync_done():
    """Le champ f3_sync_done existe sur RapportJournalier avec False par défaut."""
    champ = RapportJournalier._meta.get_field("f3_sync_done")
    assert isinstance(champ, models.BooleanField)
    assert champ.default is False
    assert str(champ.verbose_name) == "synchronisé avec F3"
    assert "quantités du rapport approuvé" in str(champ.help_text)
