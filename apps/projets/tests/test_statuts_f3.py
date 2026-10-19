"""Tests de conformité SFD F3 §7 — Statuts automatiques et tâche de nuit 00h01.

Vérifie :
1. Transitions automatiques :
   - EN_ATTENTE -> EN_COURS, uniquement si date de début atteinte ET rapport F2 soumis.
   - EN_COURS -> EN_RETARD au franchissement de delta > 5.0 (ex: 5.01 pts).
   - EN_COURS / EN_RETARD -> CRITIQUE au franchissement de delta > 25.0 (ex: 25.01 pts)
     OU indice_sante < 40 (ex: 39).
   - CRITIQUE -> EN_RETARD (et jamais directement EN_COURS) quand tout redevient normal.
   - EN_RETARD -> EN_COURS à l'évaluation suivante après rétablissement.
2. Préservation absolue des statuts manuels et terminaux (STATUTS_PROJET_MANUELS_FIXES).
3. Rattrapage nocturne des rapports APPROUVE non synchronisés (f3_sync_done=False).
4. Exécution de la tâche Celery Beat 00h01 dans le schéma de chaque entreprise active.
5. Réévaluation du statut à la fin de synchroniser_rapport_approuve
   (après le recalcul de l'avancement).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.chantier.models import JournalChantier, RapportJournalier
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutProjet,
    StatutRapport,
    StatutUtilisateur,
)
from apps.projets.models import Activite, AffectationProjet, Lot, Projet
from apps.projets.services.avancement import synchroniser_rapport_approuve
from apps.projets.services.machine_etats import (
    STATUTS_PROJET_MANUELS_FIXES,
    evaluer_statut_projet,
)
from apps.projets.tasks import evaluer_f3_nuit_tous_tenants
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db


@pytest.fixture
def environnement_f3(schema_demo):
    """Initialise un environnement de test isolé pour F3."""
    admin = Utilisateur.objects.create_user(
        email="admin.f3@demo.ci",
        password="TestPassword123!",
        nom="Admin F3",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    cp = Utilisateur.objects.create_user(
        email="cp.f3@demo.ci",
        password="TestPassword123!",
        nom="Chef Projet F3",
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    client_tiers = Tiers.objects.create(
        raison_sociale="Client F3 Promotion",
        type_tiers="ENTREPRISE",
    )

    aujourdhui = timezone.localdate()

    projet = Projet.objects.create(
        reference="PRJ-F3-TEST",
        nom="Chantier Résidence F3",
        client=client_tiers,
        ville="Abidjan",
        maitre_ouvrage="SCI F3",
        chef_projet=cp,
        date_debut_prevue=aujourdhui,
        date_fin_prevue=aujourdhui + timedelta(days=30),
        statut=StatutProjet.EN_ATTENTE,
        indice_sante=100,
        budget_initial_montant=Decimal("10000000.00"),
    )

    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=cp,
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
    )

    lot = Lot.objects.create(
        projet=projet,
        code="LOT-01",
        libelle="Gros Œuvre",
        date_debut_prevue=aujourdhui,
        date_fin_prevue=aujourdhui + timedelta(days=30),
        avancement=Decimal("0.00"),
        budget_initial_montant=Decimal("10000000.00"),
    )

    return {
        "admin": admin,
        "cp": cp,
        "client": client_tiers,
        "projet": projet,
        "lot": lot,
        "aujourdhui": aujourdhui,
    }


# ==============================================================================
# 1. TRANSITION EN_ATTENTE -> EN_COURS (DÉBUT ATTEINT ET RAPPORT SOUMIS)
# ==============================================================================


def test_transition_en_attente_vers_en_cours_exige_debut_et_rapport(environnement_f3):
    """EN_ATTENTE reste EN_ATTENTE tant que date_debut non atteinte OU aucun rapport F2."""
    env = environnement_f3
    projet = env["projet"]
    cp = env["cp"]
    j = env["aujourdhui"]

    # 1. Date de début dans le futur, aucun rapport -> reste EN_ATTENTE
    projet.date_debut_prevue = j + timedelta(days=5)
    projet.save(update_fields=["date_debut_prevue"])

    change = evaluer_statut_projet(projet, date_reference=j)
    assert change is False
    assert projet.statut == StatutProjet.EN_ATTENTE

    # 2. Date de début atteinte (aujourd'hui), mais AUCUN rapport F2 -> reste EN_ATTENTE
    projet.date_debut_prevue = j
    projet.save(update_fields=["date_debut_prevue"])

    change = evaluer_statut_projet(projet, date_reference=j)
    assert change is False
    assert projet.statut == StatutProjet.EN_ATTENTE

    # 3. Date de début dans le futur, mais un rapport F2 a été soumis
    # par anticipation -> reste EN_ATTENTE
    projet.date_debut_prevue = j + timedelta(days=5)
    projet.save(update_fields=["date_debut_prevue"])

    RapportJournalier.objects.create(
        projet=projet,
        date_rapport=j,
        statut=StatutRapport.SOUMIS,
        auteur=cp,
    )

    change = evaluer_statut_projet(projet, date_reference=j)
    assert change is False
    assert projet.statut == StatutProjet.EN_ATTENTE

    # 4. Date de début atteinte ET rapport F2 SOUMIS -> passe à EN_COURS
    projet.date_debut_prevue = j
    projet.save(update_fields=["date_debut_prevue"])

    change = evaluer_statut_projet(projet, date_reference=j)
    assert change is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_COURS


def test_transition_en_attente_avec_rapport_approuve(environnement_f3):
    """Un rapport au statut APPROUVE permet également la transition EN_ATTENTE -> EN_COURS."""
    env = environnement_f3
    projet = env["projet"]
    cp = env["cp"]
    j = env["aujourdhui"]

    projet.date_debut_prevue = j
    projet.save(update_fields=["date_debut_prevue"])

    RapportJournalier.objects.create(
        projet=projet,
        date_rapport=j,
        statut=StatutRapport.APPROUVE,
        auteur=cp,
    )

    change = evaluer_statut_projet(projet, date_reference=j)
    assert change is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_COURS


# ==============================================================================
# 2. TRANSITION EN_COURS -> EN_RETARD À 5,01 PTS
# ==============================================================================


def test_transition_en_cours_vers_en_retard_seuil_5_points(environnement_f3):
    """EN_COURS -> EN_RETARD dès qu'un lot a un delta > 5.0 (MODERE)."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    date_eval = projet.date_fin_prevue + timedelta(days=1)

    projet.statut = StatutProjet.EN_COURS
    projet.save(update_fields=["statut"])

    # Seuil exact : avancement temporel = 100.0%
    # Si avancement = 95.00%, delta = 100.0 - 95.0 = 5.00 -> pas de transition (> 5.0 requis)
    lot.avancement = Decimal("95.00")
    lot.save(update_fields=["avancement"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is False
    assert projet.statut == StatutProjet.EN_COURS

    # Si avancement = 94.99%, delta = 100.0 - 94.99 = 5.01 -> bascule EN_RETARD
    lot.avancement = Decimal("94.99")
    lot.save(update_fields=["avancement"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_RETARD


# ==============================================================================
# 3. TRANSITION VERS CRITIQUE À 25,01 PTS OU INDICE 39
# ==============================================================================


def test_transition_vers_critique_delta_25_points(environnement_f3):
    """Passe à CRITIQUE si un lot a un delta > 25.0 (CRITIQUE)."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    date_eval = projet.date_fin_prevue + timedelta(days=1)

    projet.statut = StatutProjet.EN_RETARD
    projet.save(update_fields=["statut"])

    # Si avancement = 75.00%, delta = 25.00 -> reste EN_RETARD
    lot.avancement = Decimal("75.00")
    lot.save(update_fields=["avancement"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is False
    assert projet.statut == StatutProjet.EN_RETARD

    # Si avancement = 74.99%, delta = 25.01 -> bascule à CRITIQUE
    lot.avancement = Decimal("74.99")
    lot.save(update_fields=["avancement"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.CRITIQUE


def test_transition_vers_critique_indice_sante_39(environnement_f3):
    """Passe à CRITIQUE si l'indice de santé est < 40 (ex: 39), même sans delta de lot."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    date_eval = projet.date_fin_prevue + timedelta(days=1)

    projet.statut = StatutProjet.EN_COURS
    lot.avancement = Decimal("100.00")  # delta = 0
    lot.save(update_fields=["avancement"])

    # Indice = 40 (seuil critique de settings.F3_SEUIL_INDICE_SANTE_CRITIQUE) -> pas critique (< 40)
    projet.indice_sante = settings.F3_SEUIL_INDICE_SANTE_CRITIQUE
    projet.save(update_fields=["statut", "indice_sante"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is False
    assert projet.statut == StatutProjet.EN_COURS

    # Indice = 39 -> bascule à CRITIQUE
    projet.indice_sante = 39
    projet.save(update_fields=["indice_sante"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.CRITIQUE


# ==============================================================================
# 4. RÈGLE DE RETOUR : CRITIQUE -> EN_RETARD (JAMAIS DIRECTEMENT EN_COURS)
# ==============================================================================


def test_regle_retour_critique_repasse_en_retard_puis_en_cours(environnement_f3):
    """Un projet CRITIQUE qui ne l'est plus repasse EN_RETARD, jamais directement EN_COURS."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    date_eval = projet.date_fin_prevue + timedelta(days=1)

    # État initial : projet CRITIQUE
    projet.statut = StatutProjet.CRITIQUE
    projet.indice_sante = 35
    lot.avancement = Decimal("70.00")
    projet.save(update_fields=["statut", "indice_sante"])
    lot.save(update_fields=["avancement"])

    # Tout redevient normal : avancement 100% (delta 0), indice de santé rétabli à 90
    lot.avancement = Decimal("100.00")
    lot.save(update_fields=["avancement"])
    projet.indice_sante = 90
    projet.save(update_fields=["indice_sante"])

    # Première évaluation : doit repasser EN_RETARD, et NON EN_COURS
    change1 = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change1 is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_RETARD

    # Deuxième évaluation : les conditions étant toujours normales, repasse EN_COURS
    change2 = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change2 is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_COURS


# ==============================================================================
# 5. TRANSITION EN_RETARD -> EN_COURS
# ==============================================================================


def test_transition_en_retard_vers_en_cours(environnement_f3):
    """Un projet EN_RETARD revient EN_COURS dès que son delta repasse sous 5 pts."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    date_eval = projet.date_fin_prevue + timedelta(days=1)

    projet.statut = StatutProjet.EN_RETARD
    projet.indice_sante = 80
    lot.avancement = Decimal("90.00")  # delta = 10 pts (> 5 pts)
    projet.save(update_fields=["statut", "indice_sante"])
    lot.save(update_fields=["avancement"])

    # Le lot rattrape son retard : avancement = 96.00% -> delta = 4.0 pts (<= 5 pts)
    lot.avancement = Decimal("96.00")
    lot.save(update_fields=["avancement"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is True
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_COURS


# ==============================================================================
# 6. STATUTS MANUELS ET TERMINAUX JAMAIS MODIFIÉS
# ==============================================================================


@pytest.mark.parametrize("statut_manuel", list(STATUTS_PROJET_MANUELS_FIXES))
def test_statuts_manuels_fixes_jamais_modifies(environnement_f3, statut_manuel):
    """Tous les statuts de STATUTS_PROJET_MANUELS_FIXES sont préservés."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    date_eval = projet.date_fin_prevue + timedelta(days=1)

    projet.statut = statut_manuel
    projet.indice_sante = 10  # Condition très critique
    lot.avancement = Decimal("0.00")  # Delta maximal = 100%
    projet.save(update_fields=["statut", "indice_sante"])
    lot.save(update_fields=["avancement"])

    change = evaluer_statut_projet(projet, date_reference=date_eval)
    assert change is False
    projet.refresh_from_db()
    assert projet.statut == statut_manuel


# ==============================================================================
# 7. TÂCHE DE NUIT : RATTRAPAGE D'UN RAPPORT APPROUVE NON SYNCHRONISÉ
# ==============================================================================


def test_tache_nuit_rattrape_rapport_approuve_non_synchronise(environnement_f3):
    """La tâche Celery 00h01 rattrape un rapport APPROUVE dont f3_sync_done est faux."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    cp = env["cp"]
    j = env["aujourdhui"]

    # Création d'une activité sur le lot
    act = Activite.objects.create(
        lot=lot,
        libelle="Fondations Béton",
        quantite_prevue=Decimal("100.000"),
        quantite_realisee=Decimal("0.000"),
        avancement=Decimal("0.00"),
        date_debut_prevue=j,
        date_fin_prevue=j + timedelta(days=10),
    )

    # Rapport approuvé mais avec f3_sync_done=False (simulation coupure serveur)
    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=j,
        statut=StatutRapport.APPROUVE,
        f3_sync_done=False,
        auteur=cp,
    )
    JournalChantier.objects.create(
        rapport=rapport,
        saisie={
            "activites": [
                {
                    "activite_id": str(act.id),
                    "quantite_jour": 45,
                }
            ]
        },
    )

    # Exécution de la tâche nocturne 00h01
    rapport_nuit = evaluer_f3_nuit_tous_tenants()
    assert "demo" in rapport_nuit
    assert rapport_nuit["demo"]["rapports_rattrapes"] >= 1

    # Vérification que le rapport a bien été synchronisé
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is True

    # Vérification de la propagation sur l'activité, le lot et le projet
    act.refresh_from_db()
    assert act.quantite_realisee == Decimal("45.000")
    assert act.avancement == Decimal("45.00")

    lot.refresh_from_db()
    assert lot.avancement == Decimal("45.00")

    projet.refresh_from_db()
    assert projet.avancement_reel == Decimal("45.00")


# ==============================================================================
# 8. TÂCHE DE NUIT : EXÉCUTION DANS LE SCHÉMA DE CHAQUE ENTREPRISE
# ==============================================================================


def test_tache_nuit_tourne_dans_le_schema_de_chaque_entreprise(environnement_f3):
    """Vérifie que la tâche de nuit parcourt tous les schémas tenants actifs (demo et tenant_b)."""
    env = environnement_f3
    projet_demo = env["projet"]
    cp_demo = env["cp"]
    j = env["aujourdhui"]

    # Projet demo en attente qui doit démarrer
    projet_demo.date_debut_prevue = j
    projet_demo.save(update_fields=["date_debut_prevue"])
    RapportJournalier.objects.create(
        projet=projet_demo,
        date_rapport=j,
        statut=StatutRapport.SOUMIS,
        auteur=cp_demo,
    )

    # Projet sur tenant_b
    with schema_context("tenant_b"):
        client_b = Tiers.objects.create(
            raison_sociale="Client Tenant B",
            type_tiers="ENTREPRISE",
        )
        cp_b = Utilisateur.objects.create_user(
            email="cp.b@tenant-b.ci",
            password="TestPassword123!",
            nom="Chef B",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )
        projet_b = Projet.objects.create(
            reference="PRJ-TENANT-B",
            nom="Chantier Tenant B",
            client=client_b,
            ville="San Pedro",
            chef_projet=cp_b,
            date_debut_prevue=j,
            date_fin_prevue=j + timedelta(days=20),
            statut=StatutProjet.EN_ATTENTE,
        )
        RapportJournalier.objects.create(
            projet=projet_b,
            date_rapport=j,
            statut=StatutRapport.SOUMIS,
            auteur=cp_b,
        )

    # Exécution globale
    rapport = evaluer_f3_nuit_tous_tenants()

    assert "demo" in rapport
    assert "tenant_b" in rapport

    # Vérification que le projet demo a été mis à jour dans son schéma
    projet_demo.refresh_from_db()
    assert projet_demo.statut == StatutProjet.EN_COURS

    # Vérification que le projet tenant_b a été mis à jour dans son schéma
    with schema_context("tenant_b"):
        projet_b.refresh_from_db()
        assert projet_b.statut == StatutProjet.EN_COURS


# ==============================================================================
# 9. RÉÉVALUATION DU STATUT APRÈS CHAQUE APPROBATION (SYNCHRONISER_RAPPORT_APPROUVE)
# ==============================================================================


def test_statut_reevalue_apres_approbation_dans_la_meme_transaction(environnement_f3):
    """À la fin de synchroniser_rapport_approuve, evaluer_statut_projet est exécuté."""
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    cp = env["cp"]
    j = env["aujourdhui"]

    # Projet initialement EN_ATTENTE
    projet.date_debut_prevue = j
    projet.statut = StatutProjet.EN_ATTENTE
    projet.save(update_fields=["date_debut_prevue", "statut"])

    act = Activite.objects.create(
        lot=lot,
        libelle="Terrassement Initial",
        quantite_prevue=Decimal("50.000"),
        quantite_realisee=Decimal("0.000"),
        date_debut_prevue=j,
        date_fin_prevue=j + timedelta(days=10),
    )

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=j,
        statut=StatutRapport.APPROUVE,
        f3_sync_done=False,
        auteur=cp,
    )
    JournalChantier.objects.create(
        rapport=rapport,
        saisie={
            "activites": [
                {
                    "activite_id": str(act.id),
                    "quantite_jour": 25,
                }
            ]
        },
    )

    succes = synchroniser_rapport_approuve(rapport.id)
    assert succes is True

    # Le statut du projet a été réévalué : comme début atteint et rapport approuvé -> EN_COURS
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_COURS
    assert projet.avancement_reel == Decimal("50.00")


def test_synchroniser_rapport_recalcule_avancement_avant_evaluer_statut(environnement_f3):
    """Prouve que synchroniser_rapport_approuve recalcule l'avancement AVANT d'évaluer le statut.

    Scénario :
    - Projet EN_RETARD, indice_sante=100.
    - Lot budgété terminé hier (avancement temporel = 100.0% à la date d'aujourd'hui).
    - Activité sur ce lot : quantite_prevue=100, quantite_realisee=90 -> avancement=90%.
      Delta initial = 100.0 - 90.0 = 10.0 pts (> 5 pts MODERE).
    - Rapport APPROUVE avec journal apportant quantite_jour=6 -> nouvelle quantite_realisee=96.
      Nouvel avancement = 96%, nouveau delta = 4.0 pts (<= 5 pts).
    - Si l'évaluation de statut intervenait AVANT le recalcul de l'avancement, le projet
      resterait EN_RETARD (delta 10 pts).
    - Comme le recalcul a lieu AVANT l'évaluation du statut, le delta tombe à 4.0 pts et le projet
      bascule immédiatement à EN_COURS.
    """
    env = environnement_f3
    projet = env["projet"]
    lot = env["lot"]
    cp = env["cp"]
    j = env["aujourdhui"]

    # Configuration des dates pour que l'avancement temporel soit exactement 100.0% aujourd'hui
    hier = j - timedelta(days=1)
    dix_jours_avant = j - timedelta(days=10)

    projet.date_debut_prevue = dix_jours_avant
    projet.date_fin_prevue = hier
    projet.statut = StatutProjet.EN_RETARD
    projet.indice_sante = 100
    projet.save(update_fields=["date_debut_prevue", "date_fin_prevue", "statut", "indice_sante"])

    lot.date_debut_prevue = dix_jours_avant
    lot.date_fin_prevue = hier
    lot.date_debut_baseline = dix_jours_avant
    lot.date_fin_baseline = hier
    lot.budget_initial_montant = Decimal("10000000.00")
    lot.avancement = Decimal("90.00")
    lot.save(
        update_fields=[
            "date_debut_prevue",
            "date_fin_prevue",
            "date_debut_baseline",
            "date_fin_baseline",
            "budget_initial_montant",
            "avancement",
        ]
    )

    act = Activite.objects.create(
        lot=lot,
        libelle="Bétonnage Lot 01",
        quantite_prevue=Decimal("100.000"),
        quantite_realisee=Decimal("90.000"),
        avancement=Decimal("90.00"),
        date_debut_prevue=dix_jours_avant,
        date_fin_prevue=hier,
    )

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=j,
        statut=StatutRapport.APPROUVE,
        f3_sync_done=False,
        auteur=cp,
    )
    JournalChantier.objects.create(
        rapport=rapport,
        saisie={
            "activites": [
                {
                    "activite_id": str(act.id),
                    "quantite_jour": 6,
                }
            ]
        },
    )

    succes = synchroniser_rapport_approuve(rapport.id)
    assert succes is True

    # Vérifications
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is True

    act.refresh_from_db()
    assert act.quantite_realisee == Decimal("96.000")
    assert act.avancement == Decimal("96.00")

    lot.refresh_from_db()
    assert lot.avancement == Decimal("96.00")

    projet.refresh_from_db()
    assert projet.avancement_reel == Decimal("96.00")
    # Prouve que le statut a été évalué APRÈS le recalcul (delta = 4.0 <= 5.0 -> EN_COURS)
    assert projet.statut == StatutProjet.EN_COURS
