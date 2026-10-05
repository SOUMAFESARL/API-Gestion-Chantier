"""Tests d'intégration des déclencheurs réactifs, verrou Redis, tâches Celery et alerte email vers le ROUGE.

Vérifie :
1. Comportement du verrou Redis (clé posée à la planification, effacée au début de la tâche).
2. Recalcul asynchrone et persistance de l'indice de santé et du snapshot.
3. Transition vers le ROUGE : envoi d'un SEUL email d'alerte lors de la bascule vers le rouge.
4. Absence de doublon : si le projet est déjà rouge, aucun second email n'est envoyé lors des recalculs suivants.
5. Destinataires : Chef de Projet et Direction Générale (ADMIN/DG).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.chantier.models import Blocage, RapportJournalier
from apps.chantier.services.blocage import creer_blocage, resoudre_blocage
from apps.chantier.services.rapport_journalier import creer_rapport_journalier
from apps.core.enums import BadgeSante, RoleGlobal, RoleProjet, SeveriteBlocage, StatutBlocage, StatutProjet, StatutRapport
from apps.projets.models import AffectationProjet, ArretChantier, Lot, Projet, SanteProjetSnapshot
from apps.projets.services.arret_chantier import declarer_arret_chantier
from apps.projets.services.sante_declencheur import declencher_recalcul_sante, obtenir_cle_recalcul_en_attente
from apps.projets.services.sante_email import obtenir_destinataires_alerte_rouge
from apps.projets.tasks import evaluer_sante_projets_quotidien_tous_tenants, recalculer_sante_projet_task

pytestmark = pytest.mark.django_db


@pytest.fixture
def environnement_sante(schema_demo):
    """Prépare un projet avec Chef de Projet, DG et Administrateur."""
    dg = Utilisateur.objects.create_user(
        email="dg@demo.ci",
        password="TestPassword123!",
        nom="Directeur Général",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
    )
    admin = Utilisateur.objects.create_user(
        email="admin@demo.ci",
        password="TestPassword123!",
        nom="Administrateur",
        role_global=RoleGlobal.ADMIN,
    )
    chef_projet = Utilisateur.objects.create_user(
        email="chef.projet@demo.ci",
        password="TestPassword123!",
        nom="Chef Projet",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
    )
    autre_user = Utilisateur.objects.create_user(
        email="autre@demo.ci",
        password="TestPassword123!",
        nom="Observateur",
        role_global=RoleGlobal.VISITEUR,
    )

    projet = Projet.objects.create(
        reference="PRJ-SANTE-01",
        nom="Chantier Résidence Ivoire",
        ville="Abidjan",
        chef_projet=chef_projet,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
        date_debut_baseline=date(2026, 10, 1),
        date_fin_baseline=date(2026, 10, 31),
        date_debut_reelle=date(2026, 10, 1),
        statut=StatutProjet.EN_COURS,
        badge_sante=BadgeSante.VERT,
        indice_sante=100,
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=chef_projet,
        role_projet=RoleProjet.CHEF_PROJET,
    )

    lot = Lot.objects.create(
        projet=projet,
        code="L-01",
        libelle="Gros Œuvre",
        budget_initial_montant=100000000,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
        date_debut_baseline=date(2026, 10, 1),
        date_fin_baseline=date(2026, 10, 31),
    )

    return {
        "schema": schema_demo,
        "projet": projet,
        "lot": lot,
        "dg": dg,
        "admin": admin,
        "chef_projet": chef_projet,
        "autre_user": autre_user,
    }


def test_verrou_redis_et_cycle_vie_cle(environnement_sante):
    """Vérifie que la clé 'en attente' est posée au déclenchement et effacée au début de la tâche."""
    schema = environnement_sante["schema"]
    projet = environnement_sante["projet"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)

    # Initialement vide
    assert cache.get(cle) is None

    # Premier déclenchement -> pose la clé
    planifie = declencher_recalcul_sante(projet.id, "TEST_EVENT")
    assert planifie is True
    assert cache.get(cle) == 1

    # Deuxième déclenchement immédiat -> dédupliqué
    planifie_doublon = declencher_recalcul_sante(projet.id, "TEST_EVENT_2")
    assert planifie_doublon is False

    # Exécution de la tâche Celery -> efface la clé dès le début
    with patch("apps.projets.services.sante_calculs.obtenir_jours_feries_ci", return_value=(set(), False)):
        recalculer_sante_projet_task(schema, str(projet.id), "TEST_EVENT")

    # La clé a été effacée
    assert cache.get(cle) is None

    # Un nouvel événement intervenant maintenant peut immédiatement reposer la clé
    assert declencher_recalcul_sante(projet.id, "NOUVEL_EVENT") is True
    assert cache.get(cle) == 1


def test_destinataires_alerte_rouge(environnement_sante):
    """Vérifie la détection exacte du chef de projet et des DG/Admin sans doublon."""
    projet = environnement_sante["projet"]
    destinataires = obtenir_destinataires_alerte_rouge(projet)

    assert "chef.projet@demo.ci" in destinataires
    assert "dg@demo.ci" in destinataires
    assert "admin@demo.ci" in destinataires
    assert "autre@demo.ci" not in destinataires
    # Aucune duplication
    assert len(destinataires) == len(set(destinataires))


def test_transition_vers_le_rouge_un_seul_email(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie qu'un unique email est envoyé lors de la transition vers le ROUGE, et zéro si déjà rouge."""
    schema = environnement_sante["schema"]
    projet = environnement_sante["projet"]
    lot = environnement_sante["lot"]
    chef = environnement_sante["chef_projet"]

    # Initialement VERT
    assert projet.badge_sante == BadgeSante.VERT
    mail.outbox.clear()

    # Déclenchons une situation critique qui fait plonger le projet en ROUGE
    # Création de 2 blocages critiques vieux de 10 jours ouvrés (poids 15*2 * 2 = 60 pts -> plafond 40)
    # Retard massif : 30 pts de retard -> pénalité délais 40 pts
    # Score = 100 - (40 + 40 + 20) = 0 -> ROUGE
    b1 = Blocage.objects.create(
        projet=projet,
        lot=lot,
        titre="Blocage critique 1",
        severite=SeveriteBlocage.CRITIQUE,
        statut=StatutBlocage.OUVERT,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0)),
        ouvert_par=chef,
        cree_par=chef,
    )
    b2 = Blocage.objects.create(
        projet=projet,
        lot=lot,
        titre="Blocage critique 2",
        severite=SeveriteBlocage.CRITIQUE,
        statut=StatutBlocage.OUVERT,
        ouvert_le=timezone.make_aware(datetime(2026, 10, 1, 8, 0)),
        ouvert_par=chef,
        cree_par=chef,
    )

    with django_capture_on_commit_callbacks(execute=True):
        with patch("apps.projets.services.sante_calculs.obtenir_jours_feries_ci", return_value=(set(), False)):
            res = recalculer_sante_projet_task(schema, str(projet.id), "TEST_DEGRADE")

    assert res["badge"] == BadgeSante.ROUGE
    assert res["alerte_rouge"] is True

    # Vérification de l'envoi d'email
    assert len(mail.outbox) == 1
    email_envoye = mail.outbox[0]
    assert "Passage au ROUGE" in email_envoye.subject
    assert "chef.projet@demo.ci" in email_envoye.to
    assert "dg@demo.ci" in email_envoye.to

    # Snapshot créé
    assert SanteProjetSnapshot.objects.filter(projet=projet).count() == 1
    snap = SanteProjetSnapshot.objects.filter(projet=projet).first()
    assert snap.badge_final == BadgeSante.ROUGE

    # Deuxième recalcul alors que le projet est DÉJÀ ROUGE :
    # Aucun second email ne doit être envoyé !
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        with patch("apps.projets.services.sante_calculs.obtenir_jours_feries_ci", return_value=(set(), False)):
            res_2 = recalculer_sante_projet_task(schema, str(projet.id), "TEST_RECALCUL_SUIVANT")

    assert res_2["badge"] == BadgeSante.ROUGE
    assert res_2["alerte_rouge"] is False
    assert len(mail.outbox) == 0  # ZÉRO email supplémentaire (pas de spam/doublon)


def test_evaluer_sante_projets_quotidien_tous_tenants(environnement_sante):
    """Vérifie le parcours multi-tenant de la tâche Beat quotidienne à 00h15."""
    with patch("apps.projets.services.sante_calculs.obtenir_jours_feries_ci", return_value=(set(), False)):
        rapport = evaluer_sante_projets_quotidien_tous_tenants()

    assert isinstance(rapport, dict)
    schema = environnement_sante["schema"]
    assert schema in rapport
    assert rapport[schema]["projets_actifs_recalcules"] >= 1

