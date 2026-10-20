"""Tests unitaires et d'intégration de la détection des alertes de retard et déduplication (F3).

Spécifications :
- SFD F3 v1.0 §5.4 (Vue Alertes et Retards Détectés)
- SFD F3 v1.0 §10 (Modèle AlerteRetard)
- RG-F3-07 (Détection retards — déduplication des alertes Celery)
- Erratum SFD F3 v1.0.1 (E-3)
- Tâches 147 (Causes & actions recommandées) et 148 (Déduplication seuils)
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import Role, Utilisateur
from apps.chantier.models import Blocage, JournalChantier, RapportJournalier
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    SeveriteBlocage,
    StatutBlocage,
    StatutProjet,
    StatutRapport,
)
from apps.projets.models import (
    AffectationProjet,
    AlerteRetard,
    Lot,
    NiveauAlerteRetard,
    Projet,
    StatutAlerteRetard,
)
from apps.projets.services.alertes_retard import (
    ACTION_PAR_DEFAUT,
    TABLE_ACTIONS_RECOMMANDEES,
    detecter_alertes_retard,
    extraire_causes_alerte,
    obtenir_destinataires_alerte,
)


@pytest.fixture
def projet_de_test(schema_demo):
    """Crée un projet de test avec un lot et des dates de référence."""
    cp = Utilisateur.objects.create(
        email="cp.test@demo.ci",
        nom="Kouassi",
        prenom="Jean",
        role_global=RoleGlobal.CHEF_PROJET,
    )
    ct = Utilisateur.objects.create(
        email="ct.test@demo.ci",
        nom="Konan",
        prenom="Paul",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
    )
    projet = Projet.objects.create(
        reference="PRJ-ALERTE-001",
        nom="Chantier Résidence Palmier",
        ville="Abidjan",
        statut=StatutProjet.EN_COURS,
        chef_projet=cp,
        conducteur_travaux=ct,
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 6, 30),
        date_debut_baseline=date(2026, 1, 1),
        date_fin_baseline=date(2026, 6, 30),
    )
    lot = Lot.objects.create(
        projet=projet,
        code="LOT-01",
        libelle="Gros œuvre",
        budget_initial_montant=100000000,
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 6, 30),
        date_debut_baseline=date(2026, 1, 1),
        date_fin_baseline=date(2026, 6, 30),
    )
    return projet, lot, cp, ct


# ==============================================================================
# 1. TESTS DES SEUILS EXACTS DE CHAQUE NIVEAU
# ==============================================================================


@pytest.mark.django_db
def test_seuils_niveaux(schema_demo, projet_de_test):
    """Vérifie chaque niveau à ses seuils exacts :

    - delta <= 5      (ex. 5.0)  -> rien
    - delta > 5       (ex. 5.01) -> MODERE
    - delta > 15      (ex. 15.01)-> ELEVE
    - delta > 25      (ex. 25.01)-> CRITIQUE
    """
    projet, lot, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    # 1. Borne 5.0 -> Rien
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=5.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 0

    # 2. Juste au-dessus du seuil modéré : 5.01 -> MODERE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=5.01):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        assert alertes[0].niveau == NiveauAlerteRetard.MODERE
        assert float(alertes[0].delta_pts) == pytest.approx(5.01)
        assert alertes[0].lot == lot
        assert alertes[0].statut == StatutAlerteRetard.OUVERTE

    # Nettoyage pour tester le palier suivant
    AlerteRetard.objects.all().delete()

    # 3. Juste au-dessus du seuil élevé : 15.01 -> ELEVE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=15.01):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        assert alertes[0].niveau == NiveauAlerteRetard.ELEVE
        assert float(alertes[0].delta_pts) == pytest.approx(15.01)

    AlerteRetard.objects.all().delete()

    # 4. Juste au-dessus du seuil critique : 25.01 -> CRITIQUE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=25.01):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        assert alertes[0].niveau == NiveauAlerteRetard.CRITIQUE
        assert float(alertes[0].delta_pts) == pytest.approx(25.01)


@pytest.mark.django_db
def test_seuils_dynamiques_depuis_settings_override(schema_demo, projet_de_test):
    """Vérifie que les seuils viennent de settings.F3_SEUILS_RETARD_PTS :

    avec override_settings(F3_SEUILS_RETARD_PTS={"MODERE": 10, "ELEVE": 20, "CRITIQUE": 30}) :
    - un delta à 8 ne crée rien
    - un delta à 10.01 crée une MODERE
    """
    projet, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    with override_settings(
        F3_SEUILS_RETARD_PTS={"MODERE": 10, "ELEVE": 20, "CRITIQUE": 30}
    ):
        # 1. Delta à 8 -> ne crée rien
        with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
            alertes = detecter_alertes_retard(projet, date_reference=date_ref)
            assert len(alertes) == 0

        # 2. Delta à 10.01 -> crée une alerte MODERE
        with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=10.01):
            alertes = detecter_alertes_retard(projet, date_reference=date_ref)
            assert len(alertes) == 1
            assert alertes[0].niveau == NiveauAlerteRetard.MODERE
            assert float(alertes[0].delta_pts) == pytest.approx(10.01)


# ==============================================================================
# 2. DÉDUPLICATION (RG-F3-07)
# ==============================================================================


@pytest.mark.django_db
def test_saut_direct_critique_deduplication(schema_demo, projet_de_test):
    """De 0 à 28 points d'un coup, UNE SEULE alerte CRITIQUE est créée (tâche 148)."""
    projet, lot, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=28.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        assert alertes[0].niveau == NiveauAlerteRetard.CRITIQUE
        assert float(alertes[0].delta_pts) == pytest.approx(28.0)

    # Vérification en base : exactement une seule alerte créée, pas 3 alertes simultanées
    assert AlerteRetard.objects.filter(projet=projet, lot=lot).count() == 1


@pytest.mark.django_db
def test_modere_ouverte_puis_10_points_ne_cree_rien(schema_demo, projet_de_test):
    """Une alerte MODERE ouverte puis une évaluation à 10 points ne crée rien."""
    projet, lot, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    # 1. Détection initiale à 8 points -> crée une alerte MODERE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        alertes_initiales = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes_initiales) == 1
        assert alertes_initiales[0].niveau == NiveauAlerteRetard.MODERE

    # 2. Nouvelle évaluation à 10 points (niveau MODERE) -> ne crée rien
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=10.0):
        nouvelles_alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(nouvelles_alertes) == 0

    assert AlerteRetard.objects.filter(projet=projet, lot=lot).count() == 1


@pytest.mark.django_db
def test_modere_ouverte_puis_20_points_cree_eleve(schema_demo, projet_de_test):
    """Une alerte MODERE ouverte puis une évaluation à 20 points crée une alerte ELEVE."""
    projet, lot, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    # 1. Détection initiale à 8 points -> crée une alerte MODERE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        alertes_modere = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes_modere) == 1
        assert alertes_modere[0].niveau == NiveauAlerteRetard.MODERE

    # 2. Nouvelle évaluation à 20 points -> crée une alerte ELEVE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=20.0):
        alertes_eleve = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes_eleve) == 1
        assert alertes_eleve[0].niveau == NiveauAlerteRetard.ELEVE

    # Les deux alertes coexistent en base
    assert AlerteRetard.objects.filter(projet=projet, lot=lot).count() == 2


@pytest.mark.django_db
def test_recreation_apres_resolution(schema_demo, projet_de_test):
    """Après résolution de toutes les alertes, une alerte MODERE peut se recréer."""
    projet, lot, cp, _ = projet_de_test
    date_ref = date(2026, 3, 1)

    # 1. Création d'une alerte MODERE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        alerte = alertes[0]

    # 2. Clôture / Résolution de l'alerte
    alerte.statut = StatutAlerteRetard.RESOLUE
    alerte.commentaire_resolution = "Effectifs renforcés et retard rattrapé."
    alerte.resolue_le = timezone.now()
    alerte.resolue_par = cp
    alerte.save()

    # 3. Nouvelle évaluation à 8 points -> doit pouvoir recréer une alerte MODERE
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        nouvelles_alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(nouvelles_alertes) == 1
        assert nouvelles_alertes[0].niveau == NiveauAlerteRetard.MODERE
        assert nouvelles_alertes[0].statut == StatutAlerteRetard.OUVERTE

    assert AlerteRetard.objects.filter(projet=projet, lot=lot).count() == 2


# ==============================================================================
# 3. ALERTE DE PROJET (INDICE DE SANTÉ < 40)
# ==============================================================================


@pytest.mark.django_db
def test_indice_sante_critique_projet(schema_demo, projet_de_test):
    """Indice de santé 39 -> alerte CRITIQUE au niveau projet (avec lot null)."""
    projet, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    projet.indice_sante = 39
    projet.save(update_fields=["indice_sante"])

    # Lot sans retard (delta <= 5)
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=2.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        alerte_proj = alertes[0]
        assert alerte_proj.lot is None
        assert alerte_proj.projet == projet
        assert alerte_proj.niveau == NiveauAlerteRetard.CRITIQUE
        assert alerte_proj.indice_sante == 39
        assert alerte_proj.delta_pts is None
        assert alerte_proj.statut == StatutAlerteRetard.OUVERTE

        # Une seconde détection ne recrée pas l'alerte (déduplication projet)
        alertes_bis = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes_bis) == 0


@pytest.mark.django_db
def test_indice_sante_seuil_40_ne_cree_aucune_alerte(schema_demo, projet_de_test):
    """Un indice_sante à 40 ne crée aucune alerte (seuil F3_SEUIL_INDICE_SANTE_CRITIQUE)."""
    projet, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    projet.indice_sante = 40
    projet.save(update_fields=["indice_sante"])

    # Lot sans retard
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=2.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 0


# ==============================================================================
# 4. DESTINATAIRES PAR NIVEAU
# ==============================================================================


@pytest.mark.django_db
def test_destinataires_par_niveau(schema_demo, projet_de_test):
    """Vérifie les destinataires notifiés par niveau :

    - MODERE   : CT et CP du projet
    - ELEVE    : CT + CP + utilisateurs DO
    - CRITIQUE : CT + CP + DO + DG
    """
    projet, _, cp, ct = projet_de_test

    # Affectation explicite CP et CT supplémentaire pour valider la recherche
    ct2 = Utilisateur.objects.create(
        email="ct2@demo.ci",
        nom="Yao",
        prenom="Serge",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=ct2,
        role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
        est_actif=True,
    )

    # Utilisateur DO (Directeur des Opérations)
    Role.objects.get_or_create(code="DO", defaults={"libelle": "Directeur des Opérations"})
    do_user = Utilisateur.objects.create(
        email="do@demo.ci",
        nom="Bamba",
        prenom="Awa",
        role_global="DO",
    )

    # Utilisateur DG (Directeur Général)
    Role.objects.get_or_create(code="DG", defaults={"libelle": "Directeur Général"})
    dg_user = Utilisateur.objects.create(
        email="dg@demo.ci",
        nom="Soro",
        prenom="Guillaume",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        is_owner=True,
    )

    # Autre utilisateur non concerné
    Utilisateur.objects.create(
        email="cc@demo.ci",
        nom="Traore",
        prenom="Moussa",
        role_global=RoleGlobal.CHEF_CHANTIER,
    )

    # 1. MODERE : CT et CP uniquement
    dests_modere = set(obtenir_destinataires_alerte(projet, NiveauAlerteRetard.MODERE))
    assert cp in dests_modere
    assert ct in dests_modere
    assert ct2 in dests_modere
    assert do_user not in dests_modere
    assert dg_user not in dests_modere

    # 2. ELEVE : CT, CP et DO
    dests_eleve = set(obtenir_destinataires_alerte(projet, NiveauAlerteRetard.ELEVE))
    assert cp in dests_eleve
    assert ct in dests_eleve
    assert ct2 in dests_eleve
    assert do_user in dests_eleve
    assert dg_user not in dests_eleve

    # 3. CRITIQUE : CT, CP, DO et DG
    dests_critique = set(obtenir_destinataires_alerte(projet, NiveauAlerteRetard.CRITIQUE))
    assert cp in dests_critique
    assert ct in dests_critique
    assert ct2 in dests_critique
    assert do_user in dests_critique
    assert dg_user in dests_critique


# ==============================================================================
# 5. CAUSES ET ACTIONS RECOMMANDÉES
# ==============================================================================


@pytest.mark.django_db
def test_causes_absences_et_blocages(schema_demo, projet_de_test):
    """Les causes comptent les absences, les blocages ouverts et les incidents."""
    projet, lot, cp, _ = projet_de_test
    date_ref = date(2026, 3, 10)

    # Rapport F2 des 7 derniers jours (2026-03-08) avec saisie effectifs et incidents
    rap = RapportJournalier.objects.create(
        projet=projet,
        lot=lot,
        date_rapport=date(2026, 3, 8),
        auteur=cp,
        statut=StatutRapport.APPROUVE,
    )
    JournalChantier.objects.create(
        rapport=rap,
        saisie={
            "effectifs": [
                {"categorie": "Maçons", "prevus": 10, "presents": 7},  # 3 absences
                {"categorie": "Ferrailleurs", "prevus": 8, "presents": 6},  # 2 absences
                {"categorie": "Manoeuvres", "prevus": 5, "presents": 5},  # 0 absence
            ],
            "incidents": [
                {
                    "cle": "inc-01",
                    "gravite": "MINEUR",
                    "description": "Retard livraison sable",
                },
                {
                    "cle": "inc-02",
                    "gravite": "SIGNIFICATIF",
                    "description": "Court-circuit grue",
                },
            ],
        },
    )

    # Rapport ancien (> 7 jours) qui ne doit pas être compté
    rap_ancien = RapportJournalier.objects.create(
        projet=projet,
        lot=lot,
        date_rapport=date(2026, 2, 1),
        auteur=cp,
        statut=StatutRapport.APPROUVE,
    )
    JournalChantier.objects.create(
        rapport=rap_ancien,
        saisie={
            "effectifs": [{"prevus": 20, "presents": 5}],
            "incidents": [{"cle": "inc-ancien"}],
        },
    )

    # Blocages sur le chantier
    Blocage.objects.create(
        projet=projet,
        lot=lot,
        titre="Arrêt centrale à béton",
        severite=SeveriteBlocage.CRITIQUE,
        statut=StatutBlocage.OUVERT,
        ouvert_par=cp,
    )
    Blocage.objects.create(
        projet=projet,
        lot=lot,
        titre="Attente validation ferraillage",
        severite=SeveriteBlocage.MINEUR,
        statut=StatutBlocage.PRIS_EN_CHARGE,
        ouvert_par=cp,
    )
    # Blocage résolu (ne doit pas être inclus)
    Blocage.objects.create(
        projet=projet,
        lot=lot,
        titre="Coupure eau résolue",
        severite=SeveriteBlocage.MINEUR,
        statut=StatutBlocage.RESOLU,
        ouvert_par=cp,
    )

    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        alerte = alertes[0]

        assert alerte.causes["absences"] == 5  # 3 + 2
        assert alerte.causes["incidents"] == 2
        assert "Arrêt centrale à béton" in alerte.causes["blocages_ouverts"]
        assert "Attente validation ferraillage" in alerte.causes["blocages_ouverts"]
        assert "Coupure eau résolue" not in alerte.causes["blocages_ouverts"]

        # Actions recommandées correspondantes
        assert TABLE_ACTIONS_RECOMMANDEES["absences"] in alerte.actions_recommandees
        assert TABLE_ACTIONS_RECOMMANDEES["blocages_ouverts"] in alerte.actions_recommandees
        assert TABLE_ACTIONS_RECOMMANDEES["incidents"] in alerte.actions_recommandees


@pytest.mark.django_db
def test_causes_fenetre_7_jours_bornes(schema_demo, projet_de_test):
    """Vérifie que la fenêtre [date_reference-6, date_reference] fait exactement 7 jours :

    - un rapport daté de date_reference-6 est compté
    - un rapport daté de date_reference-7 ne l'est pas
    """
    projet, lot, cp, _ = projet_de_test
    date_ref = date(2026, 3, 10)

    # Rapport daté de date_reference - 6 jours (2026-03-04) : doit être compté
    rap_j6 = RapportJournalier.objects.create(
        projet=projet,
        lot=lot,
        date_rapport=date_ref - timedelta(days=6),
        auteur=cp,
        statut=StatutRapport.APPROUVE,
    )
    JournalChantier.objects.create(
        rapport=rap_j6,
        saisie={
            "effectifs": [{"prevus": 10, "presents": 7}],  # 3 absences
            "incidents": [{"cle": "inc-j6"}],  # 1 incident
        },
    )

    # Rapport daté de date_reference - 7 jours (2026-03-03) : ne doit PAS être compté
    rap_j7 = RapportJournalier.objects.create(
        projet=projet,
        lot=lot,
        date_rapport=date_ref - timedelta(days=7),
        auteur=cp,
        statut=StatutRapport.APPROUVE,
    )
    JournalChantier.objects.create(
        rapport=rap_j7,
        saisie={
            "effectifs": [{"prevus": 10, "presents": 5}],  # 5 absences
            "incidents": [{"cle": "inc-j7"}],  # 1 incident
        },
    )

    # Vérification via extraire_causes_alerte
    causes = extraire_causes_alerte(projet, lot, date_ref)
    assert causes["absences"] == 3
    assert causes["incidents"] == 1

    # Vérification également via detecter_alertes_retard
    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        assert alertes[0].causes["absences"] == 3
        assert alertes[0].causes["incidents"] == 1


@pytest.mark.django_db
def test_actions_recommandees_par_defaut(schema_demo, projet_de_test):
    """En l'absence de causes spécifiques, l'action recommandée par défaut s'applique."""
    projet, *_ = projet_de_test
    date_ref = date(2026, 3, 1)

    with patch("apps.projets.services.alertes_retard.calculer_delta_lot", return_value=8.0):
        alertes = detecter_alertes_retard(projet, date_reference=date_ref)
        assert len(alertes) == 1
        alerte = alertes[0]
        assert alerte.causes["absences"] == 0
        assert alerte.causes["blocages_ouverts"] == []
        assert alerte.causes["incidents"] == 0
        assert alerte.actions_recommandees == [ACTION_PAR_DEFAUT]



# ==============================================================================
# 6. TESTS DES BRANCHEMENTS (TACHE DE NUIT ET APPROBATION RAPPORT)
# ==============================================================================


@pytest.mark.django_db
def test_branchement_synchroniser_rapport_approuve(schema_demo, projet_de_test):
    """Vérifie que synchroniser_rapport_approuve déclenche detecter_alertes_retard."""
    from apps.projets.services.avancement import synchroniser_rapport_approuve

    projet, lot, cp, _ = projet_de_test
    rap = RapportJournalier.objects.create(
        projet=projet,
        lot=lot,
        date_rapport=date(2026, 3, 1),
        auteur=cp,
        statut=StatutRapport.APPROUVE,
        f3_sync_done=False,
    )

    with patch("apps.projets.services.avancement.detecter_alertes_retard") as mock_detect:
        succes = synchroniser_rapport_approuve(rap.id)
        assert succes is True
        assert mock_detect.called
        assert mock_detect.call_args[0][0] == projet


@pytest.mark.django_db
def test_branchement_evaluer_f3_nuit_tous_tenants(schema_demo, projet_de_test):
    """Vérifie que la tâche de nuit appelle detecter_alertes_retard
    après l'évaluation du statut.
    """
    from apps.projets.tasks import evaluer_f3_nuit_tous_tenants

    _ = projet_de_test

    with patch("apps.projets.tasks.detecter_alertes_retard") as mock_detect:
        rapport = evaluer_f3_nuit_tous_tenants()
        assert isinstance(rapport, dict)
        assert mock_detect.called
