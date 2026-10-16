"""Décision du 16/10/2026 : aucun rapport attendu avant l'enregistrement du chantier.

Un chantier commencé avant son arrivée sur la plateforme ne doit pas réclamer de rapports
journaliers sur ce passé : le premier jour attendu est le plus tardif du début du chantier
et de son enregistrement.
"""

from datetime import datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from apps.chantier.services.journal import aujourdhui, premier_jour_rapport
from apps.projets.models import Projet

pytestmark = pytest.mark.django_db


def _projet(debut, enregistre_le):
    projet = Projet.objects.create(
        reference=f"PRJ-ENR-{uuid4().hex[:6]}",
        nom="Chantier ancien",
        ville="Abidjan",
        statut="EN_COURS",
        date_debut_prevue=debut,
        date_fin_prevue=debut + timedelta(days=400),
    )
    instant = datetime.combine(enregistre_le, time(9), tzinfo=ZoneInfo("Africa/Abidjan"))
    Projet.objects.filter(pk=projet.pk).update(cree_le=instant)
    projet.refresh_from_db()
    return projet


def test_chantier_anterieur_a_la_plateforme(schema_demo):
    aujourd = aujourdhui()
    projet = _projet(debut=aujourd - timedelta(days=200), enregistre_le=aujourd - timedelta(days=1))
    assert premier_jour_rapport(projet) == aujourd - timedelta(days=1)


def test_chantier_qui_commence_apres_son_enregistrement(schema_demo):
    aujourd = aujourdhui()
    projet = _projet(debut=aujourd + timedelta(days=5), enregistre_le=aujourd - timedelta(days=3))
    assert premier_jour_rapport(projet) == aujourd + timedelta(days=5)
