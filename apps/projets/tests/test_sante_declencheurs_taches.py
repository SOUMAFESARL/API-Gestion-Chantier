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


def test_verrou_redis_et_cycle_vie_cle(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie que la clé 'en attente' est posée après commit et effacée au début de la tâche."""
    schema = environnement_sante["schema"]
    projet = environnement_sante["projet"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)

    # Initialement vide
    assert cache.get(cle) is None

    # Premier déclenchement -> pose la clé après commit et appelle apply_async avec countdown=10
    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            declencher_recalcul_sante(projet.id, "TEST_EVENT")
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs["countdown"] == 10

        # Deuxième déclenchement immédiat -> dédupliqué (mock_apply n'est pas réappelé)
        with django_capture_on_commit_callbacks(execute=True):
            declencher_recalcul_sante(projet.id, "TEST_EVENT_2")
        assert cache.get(cle) == 1
        assert mock_apply.call_count == 1

    # Exécution de la tâche Celery -> efface la clé dès le début
    with patch("apps.projets.services.sante_calculs.obtenir_jours_feries_ci", return_value=(set(), False)):
        recalculer_sante_projet_task(schema, str(projet.id), "TEST_EVENT")

    # La clé a été effacée
    assert cache.get(cle) is None

    # Un nouvel événement intervenant maintenant peut immédiatement reposer la clé après commit
    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            declencher_recalcul_sante(projet.id, "NOUVEL_EVENT")
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    cache.delete(cle)


def test_destinataires_alerte_rouge(environnement_sante):
    """Vérifie la détection exacte du chef de projet et du DG uniquement (F3, sans ADMIN)."""
    projet = environnement_sante["projet"]
    destinataires = obtenir_destinataires_alerte_rouge(projet)

    assert "chef.projet@demo.ci" in destinataires
    assert "dg@demo.ci" in destinataires
    assert "admin@demo.ci" not in destinataires
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


def test_transaction_annulee_ne_bloque_pas_recalcul(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie qu'une transaction annulée (rollback) ne pose pas la clé et ne bloque pas les recalculs ultérieurs (F2)."""
    schema = environnement_sante["schema"]
    projet = environnement_sante["projet"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)

    # 1. Transaction qui échoue avec rollback
    try:
        from django.db import transaction

        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                declencher_recalcul_sante(projet.id, "TRANSACTION_ROLLBACK")
                raise RuntimeError("Erreur forçant le rollback")
    except RuntimeError:
        pass

    # La clé Redis NE DOIT PAS être posée car la transaction a été annulée
    assert cache.get(cle) is None

    # 2. Une transaction ultérieure avec commit pose la clé normalement
    from django.db import transaction

    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                declencher_recalcul_sante(projet.id, "TRANSACTION_REUSSIE")
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    cache.delete(cle)


def test_declencheur_rapport_soumission_et_creation_directe(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie que la soumission et la création directe en SOUMIS déclenchent le recalcul (F1/F6)."""
    projet = environnement_sante["projet"]
    lot = environnement_sante["lot"]
    chef = environnement_sante["chef_projet"]
    schema = environnement_sante["schema"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)
    cache.delete(cle)

    from apps.chantier.services.rapport_journalier import (
        creer_rapport_journalier,
        soumettre_rapport_journalier,
    )

    # 1. Création directe au statut SOUMIS
    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            rapport_1 = creer_rapport_journalier(
                projet=projet,
                lot=lot,
                auteur=chef,
                date_rapport=date(2026, 10, 5),
                statut=StatutRapport.SOUMIS,
            )
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    cache.delete(cle)

    # 2. Création en BROUILLON puis soumission formelle
    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            rapport_2 = creer_rapport_journalier(
                projet=projet,
                lot=lot,
                auteur=chef,
                date_rapport=date(2026, 10, 6),
                statut=StatutRapport.BROUILLON,
            )
        # En brouillon, aucun recalcul n'est déclenché
        assert cache.get(cle) is None
        mock_apply.assert_not_called()

        # Soumission du rapport -> déclenche le recalcul
        with django_capture_on_commit_callbacks(execute=True):
            soumettre_rapport_journalier(rapport=rapport_2, utilisateur=chef)
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    cache.delete(cle)


def test_declencheur_rapport_rejet(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie que le rejet d'un rapport journalier déclenche un recalcul (F1/F6)."""
    projet = environnement_sante["projet"]
    lot = environnement_sante["lot"]
    chef = environnement_sante["chef_projet"]
    schema = environnement_sante["schema"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)
    cache.delete(cle)

    from apps.chantier.services.rapport_journalier import (
        creer_rapport_journalier,
        rejeter_rapport_journalier,
    )

    rapport = creer_rapport_journalier(
        projet=projet,
        lot=lot,
        auteur=chef,
        date_rapport=date(2026, 10, 7),
        statut=StatutRapport.SOUMIS,
    )
    cache.delete(cle)

    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            rejeter_rapport_journalier(
                rapport=rapport,
                utilisateur=chef,
                motif="Motif de rejet valide de plus de vingt caractères requis.",
            )

        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    assert rapport.statut == StatutRapport.REJETE
    cache.delete(cle)


def test_declencheur_mise_a_jour_quantite_realisee(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie que la mise à jour de quantite_realisee déclenche le recalcul (F1/F6)."""
    projet = environnement_sante["projet"]
    lot = environnement_sante["lot"]
    chef = environnement_sante["chef_projet"]
    schema = environnement_sante["schema"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)
    cache.delete(cle)

    from apps.projets.models import Activite
    from apps.projets.services.activites import mettre_a_jour_quantite_realisee

    act = Activite.objects.create(
        lot=lot,
        libelle="Fouilles",
        quantite_prevue=Decimal("100.000"),
        quantite_realisee=Decimal("0.000"),
        budget_initial_montant=5000000,
        cree_par=chef,
    )

    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            mettre_a_jour_quantite_realisee(
                activite=act,
                quantite_realisee=Decimal("45.000"),
                utilisateur=chef,
            )

        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    act.refresh_from_db()
    assert act.quantite_realisee == Decimal("45.000")
    cache.delete(cle)


def test_suspension_reprise_ouverture_fermeture_arret_automatique(environnement_sante, django_capture_on_commit_callbacks):
    """Vérifie que SUSPENDU ouvre un ArretChantier et la reprise le ferme automatiquement (C2, F1, F6)."""
    projet = environnement_sante["projet"]
    chef = environnement_sante["chef_projet"]
    schema = environnement_sante["schema"]
    cle = obtenir_cle_recalcul_en_attente(schema, projet.id)
    cache.delete(cle)

    from apps.projets.services.machine_etats import changer_statut_projet

    # Initialement EN_COURS, aucun arrêt
    assert projet.arrets_chantier.filter(supprime_le__isnull=True).count() == 0

    # 1. Passage à SUSPENDU -> ouverture automatique d'un ArretChantier
    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            changer_statut_projet(projet, StatutProjet.SUSPENDU, utilisateur=chef)

        projet.refresh_from_db()
        assert projet.statut == StatutProjet.SUSPENDU
        arret_ouvert = projet.arrets_chantier.filter(supprime_le__isnull=True, date_fin__isnull=True).first()
        assert arret_ouvert is not None
        assert arret_ouvert.date_fin is None
        assert arret_ouvert.motif == "Suspension du projet"
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    cache.delete(cle)

    # 2. Reprise du projet (passage à EN_COURS) -> fermeture automatique de l'arrêt
    with patch("apps.projets.tasks.recalculer_sante_projet_task.apply_async") as mock_apply:
        with django_capture_on_commit_callbacks(execute=True):
            changer_statut_projet(projet, StatutProjet.EN_COURS, utilisateur=chef)

        projet.refresh_from_db()
        assert projet.statut == StatutProjet.EN_COURS
        arret_ferme = projet.arrets_chantier.filter(supprime_le__isnull=True).first()
        assert arret_ferme.date_fin is not None
        assert arret_ferme.date_fin == timezone.localdate()
        assert cache.get(cle) == 1
        mock_apply.assert_called_once()
    cache.delete(cle)


