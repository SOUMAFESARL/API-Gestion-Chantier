"""Test d'unification du calcul d'avancement physique (C3).

Prouve qu'il n'existe plus qu'une seule et unique valeur d'avancement pour le projet
et pour chaque lot, partagée par :
- statistiques_lots(lots)
- calculer_avancement_physique_projet(projet)
- ProjetCreationResponseSerializer.get_avancement_reel(projet)
- LotResponseSerializer.get_avancement(lot)

Démontre la correction du biais de l'ancien calcul aplati (ex: 83.33% vs 19% / 10%).
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.core.enums import StatutActivite
from apps.projets.serializers.lot import LotResponseSerializer
from apps.projets.serializers.swagger import ProjetCreationResponseSerializer
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_lot,
    calculer_avancement_physique_projet,
)
from apps.projets.services.statistiques import statistiques_lots


def test_unification_avancement_physique_exemple_biais():
    """Vérifie l'élimination du biais d'aplatissement des activités.

    Contexte :
    - Lot A (Gros Œuvre, budget 9 000 000 FCFA, 90% du projet) :
      1 activité réalisée à 10% (quantité 10 / 100).
    - Lot B (Finitions, budget 1 000 000 FCFA, 10% du projet) :
      5 petites activités réalisées à 100% (quantité 100 / 100).

    Ancien calcul (aplatissement des 6 activités sans budget unitaire) :
      (10% + 100% + 100% + 100% + 100% + 100%) / 6 = 510 / 6 = 85.0%
      (Ou si la 1ère activité était à 0% : 500 / 6 = 83.33%).
      Le projet paraissait achevé à 83-85% alors que le gros œuvre (90% du coût) n'était qu'à 10% !

    Nouveau calcul unifié (Activité -> Lot -> Projet pondéré par le budget des lots) :
      Lot A = 10.0%
      Lot B = 100.0%
      Projet = (10% * 9M + 100% * 1M) / 10M = (900 000 + 1 000 000) / 10 000 000 = 19.0%.
    """
    # 1. Configuration du Lot A
    act_a = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=10,
        budget_initial_montant=Decimal("900000000"),  # en centimes
        date_fin_prevue=None,
    )
    lot_a = MagicMock(
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("900000000"),
    )
    lot_a.activites.all.return_value = [act_a]

    # 2. Configuration du Lot B avec 5 activités
    acts_b = [
        MagicMock(
            est_actif=True,
            supprime_le=None,
            statut=StatutActivite.EN_COURS,
            quantite_prevue=100,
            quantite_realisee=100,
            budget_initial_montant=Decimal("20000000"),
            date_fin_prevue=None,
        )
        for _ in range(5)
    ]
    lot_b = MagicMock(
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("100000000"),
    )
    lot_b.activites.all.return_value = acts_b

    # Configuration du Projet
    projet = MagicMock()
    projet.lots.all.return_value = [lot_a, lot_b]

    # 3. Vérification de l'avancement individuel des lots
    av_lot_a = calculer_avancement_physique_lot(lot_a)
    assert av_lot_a == 10.0

    av_lot_b = calculer_avancement_physique_lot(lot_b)
    assert av_lot_b == 100.0

    # 4. Vérification via statistiques_lots sur chaque lot individuel
    stats_lot_a = statistiques_lots([lot_a])
    assert stats_lot_a["avancement_pondere"] == 10.0
    assert stats_lot_a["activites_count"] == 1
    assert stats_lot_a["lots_count"] == 1
    assert stats_lot_a["ponderation"] == "BUDGET"

    stats_lot_b = statistiques_lots([lot_b])
    assert stats_lot_b["avancement_pondere"] == 100.0
    assert stats_lot_b["activites_count"] == 5

    # 5. Vérification au niveau projet : les 3 consommateurs donnent exactement 19.0%
    av_projet_moteur, mode_moteur = calculer_avancement_physique_projet(projet)
    assert av_projet_moteur == 19.0
    assert mode_moteur == "BUDGET"

    stats_projet = statistiques_lots([lot_a, lot_b])
    assert stats_projet["avancement_pondere"] == 19.0
    assert stats_projet["ponderation"] == "BUDGET"
    assert stats_projet["lots_count"] == 2
    assert stats_projet["activites_count"] == 6

    serializer_projet = ProjetCreationResponseSerializer()
    av_serializer = serializer_projet.get_avancement_reel(projet)
    assert av_serializer == 19.0

    # Preuve formelle de stricte égalité entre toutes les sources
    assert av_projet_moteur == stats_projet["avancement_pondere"] == av_serializer == 19.0


def test_unification_avec_repli_uniforme():
    """Si un lot n'a pas de budget initial, repli uniforme au niveau lots (50% et 50%)."""
    lot_a = MagicMock(
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=None,  # Pas de budget
    )
    act_a = MagicMock(
        est_actif=True,
        supprime_le=None,
        statut=StatutActivite.EN_COURS,
        quantite_prevue=100,
        quantite_realisee=0,
        budget_initial_montant=None,
        date_fin_prevue=None,
    )
    lot_a.activites.all.return_value = [act_a]

    # Lot B avec 5 activités à 100%
    acts_b = [
        MagicMock(
            est_actif=True,
            supprime_le=None,
            statut=StatutActivite.EN_COURS,
            quantite_prevue=100,
            quantite_realisee=100,
            budget_initial_montant=None,
            date_fin_prevue=None,
        )
        for _ in range(5)
    ]
    lot_b = MagicMock(
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=None,  # Pas de budget non plus
    )
    lot_b.activites.all.return_value = acts_b

    projet = MagicMock()
    projet.lots.all.return_value = [lot_a, lot_b]

    # Lot A = 0%, Lot B = 100%
    # Au niveau projet en repli uniforme sur les 2 lots : (0% + 100%) / 2 = 50.0%
    # (Tandis que l'ancien calcul aplati donnait 5/6 = 83.33% !)
    stats = statistiques_lots([lot_a, lot_b])
    av_moteur, mode = calculer_avancement_physique_projet(projet)

    assert stats["avancement_pondere"] == 50.0
    assert stats["ponderation"] == "UNIFORME"
    assert av_moteur == 50.0
    assert mode == "UNIFORME"
    assert stats["avancement_pondere"] == av_moteur
