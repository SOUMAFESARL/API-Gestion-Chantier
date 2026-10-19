"""Tests unitaires et d'intégration du moteur d'Indice de Santé F3 (Formule 6).

Spécification : SFD F3 §4.6, §7 & Erratum v1.0.1.
Paliers : Décisions fermes du pilotage.

Ce fichier vérifie :
1. Chaque palier de chaque score à ses bornes :
   - Délais : d = 5, 5.01, 15, 15.01
   - Rapports : taux 100, 99, 70, 69
   - Blocages : vide, [MINEUR, MINEUR], [MINEUR, MAJEUR]
   - Incidents : vide, [SIGNIFICATIF], [MINEUR, GRAVE]
2. La Formule 6 avec calcul exact et documentation de la règle d'arrondi (ROUND_HALF_UP) :
   - (100, 40, 100, 10) -> 40 + 10 + 20 + 1.5 = 71.5 -> 72
3. Les seuils de badges (VERT >= 80, ORANGE >= 50, ROUGE < 50)
4. L'évaluation en base (evaluer_indice_sante) sur un projet avec un blocage
   MAJEUR ouvert et un rapport manquant dans la semaine.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.chantier.models import Blocage, JournalChantier, RapportJournalier
from apps.core.enums import (
    BadgeSante,
    RoleGlobal,
    SeveriteBlocage,
    StatutBlocage,
    StatutProjet,
    StatutRapport,
)
from apps.projets.models import Activite, Lot, Projet
from apps.projets.services.indice_sante import (
    IndiceSante,
    determiner_badge,
    evaluer_indice_sante,
    indice_sante,
    score_blocages,
    score_delais,
    score_incidents,
    score_rapports,
)

# ==============================================================================
# 1. TESTS DES QUATRE SCORES AUX BORNES DE LEURS PALIERS
# ==============================================================================


def test_score_delais_bornes():
    """Vérifie la dimension Délais selon les paliers de pilotage :

    - d <= 5       -> 100
    - 5 < d <= 15  -> 40
    - d > 15       -> 10
    """
    # Borne 5 et juste au-dessus (5.01)
    assert score_delais(5.0) == 100
    assert score_delais(5.01) == 40

    # Borne 15 et juste au-dessus (15.01)
    assert score_delais(15.0) == 40
    assert score_delais(15.01) == 10

    # Cas d'avance (delta négatif) et zéro
    assert score_delais(0.0) == 100
    assert score_delais(-10.0) == 100

    # Retard important (> 15)
    assert score_delais(25.0) == 10


def test_score_rapports_bornes():
    """Vérifie la dimension Rapports selon les paliers de pilotage :

    - taux = 100        -> 100
    - 70 <= taux < 100  -> 40
    - taux < 70         -> 10
    """
    # 100 jours attendus pour obtenir des pourcentages entiers exacts
    assert score_rapports(attendus=100, couverts=100) == 100  # taux = 100
    assert score_rapports(attendus=100, couverts=99) == 40   # taux = 99
    assert score_rapports(attendus=100, couverts=70) == 40   # taux = 70
    assert score_rapports(attendus=100, couverts=69) == 10   # taux = 69

    # Cas limite : aucun jour attendu -> taux = 100 -> score = 100
    assert score_rapports(attendus=0, couverts=0) == 100

    # Semaine standard (5 jours ouvrés attendus)
    assert score_rapports(attendus=5, couverts=5) == 100  # 100% -> 100
    assert score_rapports(attendus=5, couverts=4) == 40   # 80%  -> 40
    assert score_rapports(attendus=5, couverts=3) == 10   # 60%  -> 10
    assert score_rapports(attendus=5, couverts=0) == 10   # 0%   -> 10


def test_score_blocages_paliers():
    """Vérifie la dimension Blocages selon les paliers de pilotage :

    - aucun                                  -> 100
    - seulement des MINEUR                   -> 40
    - au moins un MAJEUR ou un CRITIQUE      -> 10
    """
    # Aucun blocage
    assert score_blocages([]) == 100

    # Seulement des MINEUR
    assert score_blocages(["MINEUR", "MINEUR"]) == 40
    assert score_blocages(["MINEUR"]) == 40

    # Présence de MAJEUR ou CRITIQUE
    assert score_blocages(["MINEUR", "MAJEUR"]) == 10
    assert score_blocages(["MAJEUR"]) == 10
    assert score_blocages(["CRITIQUE"]) == 10
    assert score_blocages(["MINEUR", "CRITIQUE"]) == 10


def test_score_incidents_paliers():
    """Vérifie la dimension Incidents selon les paliers de pilotage :

    - aucun incident        -> 100
    - aucun incident GRAVE  -> 40
    - au moins un GRAVE     -> 10
    """
    # Aucun incident
    assert score_incidents([]) == 100

    # Aucun GRAVE (au moins un incident non-grave)
    assert score_incidents(["SIGNIFICATIF"]) == 40
    assert score_incidents(["MINEUR"]) == 40
    assert score_incidents(["MINEUR", "SIGNIFICATIF"]) == 40

    # Au moins un incident GRAVE
    assert score_incidents(["MINEUR", "GRAVE"]) == 10
    assert score_incidents(["GRAVE"]) == 10
    assert score_incidents(["SIGNIFICATIF", "GRAVE"]) == 10


# ==============================================================================
# 2. TEST DE LA FORMULE 6 (VALEURS EXACTES ET RÈGLE D'ARRONDI)
# ==============================================================================


def test_formule_6_valeurs_exactes_et_arrondi():
    """Vérifie la Formule 6 avec l'exemple exact de la consigne et la règle d'arrondi.

    Exemple prescrit :
    - s_delais = 100    (pondération 40% -> 40.0)
    - s_rapports = 40   (pondération 25% -> 10.0)
    - s_blocages = 100  (pondération 20% -> 20.0)
    - s_incidents = 10  (pondération 15% -> 1.5)
    Somme = 40.0 + 10.0 + 20.0 + 1.5 = 71.5.

    Règle d'arrondi adoptée : ROUND_HALF_UP (arrondi arithmétique standard,
    0.5 vers l'entier supérieur), ce qui donne exactement 72.
    Cette convention est identique à celle de `sante_calculs.py` pour garantir
    la cohérence globale du produit.
    """
    score = indice_sante(100, 40, 100, 10)
    assert score == 72

    # Scores parfaits -> 100
    assert indice_sante(100, 100, 100, 100) == 100

    # Scores minimaux -> 10
    assert indice_sante(10, 10, 10, 10) == 10

    # Scores moyens -> 40
    assert indice_sante(40, 40, 40, 40) == 40

    # Autre cas de demi-borne : 62.5 -> 63
    # 40*0.4 (16) + 100*0.25 (25) + 100*0.20 (20) + 10*0.15 (1.5) = 62.5 -> 63
    assert indice_sante(40, 100, 100, 10) == 63


@override_settings(
    F3_PONDERATIONS_INDICE_SANTE={
        "delais": 100,
        "rapports": 0,
        "blocages": 0,
        "incidents": 0,
    }
)
def test_formule_6_lit_settings_ponderations():
    """Vérifie que indice_sante lit dynamiquement settings.F3_PONDERATIONS_INDICE_SANTE."""
    assert indice_sante(40, 100, 100, 100) == 40


def test_determiner_badge_seuils():
    """Vérifie l'attribution du badge opérationnel selon les seuils :

    - score >= 80 -> VERT
    - 50 <= score < 80 -> ORANGE
    - score < 50 -> ROUGE
    """
    assert determiner_badge(100) == BadgeSante.VERT
    assert determiner_badge(80) == BadgeSante.VERT
    assert determiner_badge(79) == BadgeSante.ORANGE
    assert determiner_badge(50) == BadgeSante.ORANGE
    assert determiner_badge(49) == BadgeSante.ROUGE
    assert determiner_badge(0) == BadgeSante.ROUGE


# ==============================================================================
# 3. TEST EN BASE DE DONNÉES (evaluer_indice_sante)
# ==============================================================================


@pytest.mark.django_db
def test_evaluer_indice_sante_en_base(schema_demo):
    """Vérifie evaluer_indice_sante en base sur un projet complet :

    - Un blocage MAJEUR ouvert -> score_blocages = 10
    - Un rapport manquant dans la semaine (4 soumis sur 5 ouvrés attendus)
      -> score_rapports = 40
    - Aucun incident -> score_incidents = 100
    - Projet sans retard contractuel -> score_delais = 100
    Score attendu : 100*0.4 + 40*0.25 + 10*0.2 + 100*0.15 = 40 + 10 + 2 + 15 = 67.
    Badge attendu : ORANGE (car 50 <= 67 < 80).
    """
    # 1. Création de l'utilisateur auteur des rapports et blocages
    auteur = Utilisateur.objects.create(
        email="conducteur.chantier@demo.ci",
        nom="Kouassi",
        prenom="Jean",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
    )

    # 2. Création du projet
    projet = Projet.objects.create(
        reference="PRJ-TEST-S1",
        nom="Chantier Résidence Ivoire S1",
        ville="Abidjan",
        statut=StatutProjet.EN_COURS,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
        date_debut_baseline=date(2026, 10, 1),
        date_fin_baseline=date(2026, 10, 31),
    )
    # Bypasser auto_now_add pour antidater la création avant la fenêtre de test
    Projet.objects.filter(id=projet.id).update(
        cree_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0))
    )
    projet.refresh_from_db()

    # 3. Date de référence : Vendredi 16 octobre 2026
    # Fenêtre 7 jours calendaires : du Samedi 10 au Vendredi 16 octobre 2026
    # Jours ouvrés (lundi au vendredi) : 12, 13, 14, 15, 16 octobre (5 jours)
    date_ref = date(2026, 10, 16)

    # 4. Création de 4 rapports sur les 5 jours ouvrés attendus (le vendredi 16 manque)
    for jour in [12, 13, 14, 15]:
        RapportJournalier.objects.create(
            projet=projet,
            date_rapport=date(2026, 10, jour),
            auteur=auteur,
            statut=StatutRapport.SOUMIS,
        )

    # 5. Création d'un blocage MAJEUR ouvert
    Blocage.objects.create(
        projet=projet,
        titre="Panne de centrale à béton",
        severite=SeveriteBlocage.MAJEUR,
        statut=StatutBlocage.OUVERT,
        ouvert_par=auteur,
    )

    # 6. Évaluation de l'indice de santé
    res = evaluer_indice_sante(projet, date_reference=date_ref)

    # 7. Vérifications
    assert isinstance(res, IndiceSante)
    assert res.scores["delais"] == 100
    assert res.scores["rapports"] == 40
    assert res.scores["blocages"] == 10
    assert res.scores["incidents"] == 100

    assert res.taux_rapports == 80.0
    assert res.delta == 0.0
    assert res.indice == 67
    assert res.badge == BadgeSante.ORANGE
    assert isinstance(res.avertissements, list)
    assert set(res.avertissements).issubset({"JOURS_FERIES_INCOMPLETS"})


@pytest.mark.django_db
def test_evaluer_indice_sante_avec_incidents_et_lots(schema_demo):
    """Vérifie evaluer_indice_sante avec un lot, avancement et incidents."""
    auteur = Utilisateur.objects.create(
        email="chef.projet@demo.ci",
        nom="Diallo",
        prenom="Amadou",
        role_global=RoleGlobal.CHEF_PROJET,
    )

    projet = Projet.objects.create(
        reference="PRJ-TEST-S1-BIS",
        nom="Chantier Tour Palmier",
        ville="Abidjan",
        statut=StatutProjet.EN_COURS,
        budget_initial_montant=5000000000,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
        date_debut_baseline=date(2026, 10, 1),
        date_fin_baseline=date(2026, 10, 31),
    )
    Projet.objects.filter(id=projet.id).update(
        cree_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0))
    )
    projet.refresh_from_db()

    # Création d'un lot et d'une activité pour tester le prefetch et l'avancement
    lot = Lot.objects.create(
        projet=projet,
        code="LOT-01",
        libelle="Gros œuvre",
        budget_initial_montant=5000000000,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
        date_debut_baseline=date(2026, 10, 1),
        date_fin_baseline=date(2026, 10, 31),
    )
    Activite.objects.create(
        lot=lot,
        libelle="Fondations",
        quantite_prevue=100,
        quantite_realisee=100,
    )

    date_ref = date(2026, 10, 16)

    # Création des 5 rapports couvrant la totalité des 5 jours ouvrés attendus
    for jour in [12, 13, 14, 15, 16]:
        r = RapportJournalier.objects.create(
            projet=projet,
            date_rapport=date(2026, 10, jour),
            auteur=auteur,
            statut=StatutRapport.APPROUVE,
        )
        if jour == 14:
            # Ajout d'un incident significatif mais non grave sur le journal du 14
            JournalChantier.objects.create(
                rapport=r,
                saisie={
                    "incidents": [
                        {
                            "cle": "inc-01",
                            "gravite": "SIGNIFICATIF",
                            "description": "Fissure de surface constatée",
                        }
                    ]
                },
            )

    # Blocage mineur seulement
    Blocage.objects.create(
        projet=projet,
        titre="Manque d'échafaudage secondaire",
        severite=SeveriteBlocage.MINEUR,
        statut=StatutBlocage.OUVERT,
        ouvert_par=auteur,
    )

    res = evaluer_indice_sante(projet, date_reference=date_ref)

    assert res.taux_rapports == 100.0
    assert res.scores["rapports"] == 100
    assert res.scores["blocages"] == 40  # Uniquement mineur
    assert res.scores["incidents"] == 40  # Présence de SIGNIFICATIF, aucun GRAVE

    # Formule 6 :
    # Délais (delta <= 5) -> 100 * 0.40 = 40
    # Rapports -> 100 * 0.25 = 25
    # Blocages -> 40 * 0.20 = 8
    # Incidents -> 40 * 0.15 = 6
    # Total = 40 + 25 + 8 + 6 = 79 -> ORANGE (seuil VERT à 80)
    assert res.indice == 79
    assert res.badge == BadgeSante.ORANGE
