"""Tests de synchronisation F3 : les quantités approuvées alimentent l'avancement."""

# ruff: noqa: F811

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.chantier.models import JournalChantier, RapportJournalier
from apps.chantier.services.journal import aujourdhui
from apps.chantier.tests.test_journal_api import (
    API,
    corps,
    creer,
    soumettre,
    terrain,  # noqa: F401
)
from apps.core.enums import StatutRapport
from apps.projets.models import Activite
from apps.projets.services.avancement import synchroniser_rapport_approuve

pytestmark = pytest.mark.django_db


def test_integration_circuit_approbation_synchronise_avancement(
    terrain, django_capture_on_commit_callbacks
):
    """(a) Test d'intégration complet via l'API.

    Parcourt le circuit réel (CC crée et soumet, CT valide, CP approuve).
    Vérifie qu'après l'approbation du CP :
    - quantite_realisee a augmenté exactement des quantite_jour saisies
    - Activite.avancement, Lot.avancement et Projet.avancement_reel sont recalculés
    - f3_sync_done passe à True
    """
    lot = terrain["lot"]
    projet = terrain["projet"]
    activite = terrain["activite"]

    # Budgets pour que la formule 3 (pondération par budget des lots) s'applique
    lot.budget_initial_montant = 10_000_000
    lot.save(update_fields=["budget_initial_montant"])
    projet.budget_initial_montant = 10_000_000
    projet.save(update_fields=["budget_initial_montant"])

    q_init = activite.quantite_realisee  # 0.000

    identifiant = creer(terrain, data=corps(terrain))
    soumettre(terrain, identifiant)

    ct, cp = terrain["clients"]["CT"], terrain["clients"]["CP"]
    rep_ct = ct.post(
        f"{API}/rapports/{identifiant}/valider/", {"commentaire": "Conforme"}, format="json"
    )
    assert rep_ct.status_code == 200, rep_ct.data

    with django_capture_on_commit_callbacks(execute=True):
        rep_cp = cp.post(f"{API}/rapports/{identifiant}/approuver/", {}, format="json")
    assert rep_cp.status_code == 200, rep_cp.data

    activite.refresh_from_db()
    lot.refresh_from_db()
    projet.refresh_from_db()
    rapport = RapportJournalier.objects.get(pk=identifiant)

    assert rapport.f3_sync_done is True
    assert activite.quantite_realisee == q_init + Decimal("12.500")
    assert activite.avancement == Decimal("12.50")
    assert lot.avancement == Decimal("12.50")
    assert projet.avancement_reel == Decimal("12.50")


def test_idempotence_second_appel_ne_double_pas(
    terrain, django_capture_on_commit_callbacks
):
    """(b.1) Idempotence : un second appel ou resauvegarder ne double pas les quantités."""
    identifiant = creer(terrain, data=corps(terrain))
    soumettre(terrain, identifiant)
    ct, cp = terrain["clients"]["CT"], terrain["clients"]["CP"]
    ct.post(f"{API}/rapports/{identifiant}/valider/", {"commentaire": "Conforme"}, format="json")

    with django_capture_on_commit_callbacks(execute=True):
        cp.post(f"{API}/rapports/{identifiant}/approuver/", {}, format="json")

    activite = terrain["activite"]
    activite.refresh_from_db()
    assert activite.quantite_realisee == Decimal("12.500")

    # 1. Rappel direct de la fonction de synchronisation
    resultat = synchroniser_rapport_approuve(identifiant)
    assert resultat is False

    activite.refresh_from_db()
    assert activite.quantite_realisee == Decimal("12.500")

    # 2. Resauvegarder le rapport ne modifie pas les quantités
    rapport = RapportJournalier.objects.get(pk=identifiant)
    with django_capture_on_commit_callbacks(execute=True):
        rapport.save()

    activite.refresh_from_db()
    assert activite.quantite_realisee == Decimal("12.500")


def test_rapport_non_approuve_ne_change_rien(terrain):
    """(b.2) Un rapport SOUMIS, validé CT ou REJETE n'alimente rien (RG-F3-03)."""
    activite = terrain["activite"]
    q_init = activite.quantite_realisee

    identifiant = creer(terrain, data=corps(terrain))
    soumettre(terrain, identifiant)
    rapport = RapportJournalier.objects.get(pk=identifiant)
    assert rapport.statut == StatutRapport.SOUMIS

    # 1. Rapport SOUMIS
    res_soumis = synchroniser_rapport_approuve(identifiant)
    assert res_soumis is False
    activite.refresh_from_db()
    assert activite.quantite_realisee == q_init
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is False

    # 2. Rapport validé CT (statut toujours SOUMIS, valide_ct_le renseigné)
    ct = terrain["clients"]["CT"]
    ct.post(f"{API}/rapports/{identifiant}/valider/", {"commentaire": "Vu"}, format="json")
    rapport.refresh_from_db()
    assert rapport.statut == StatutRapport.SOUMIS
    assert rapport.journal.valide_ct_le is not None

    res_ct = synchroniser_rapport_approuve(identifiant)
    assert res_ct is False
    activite.refresh_from_db()
    assert activite.quantite_realisee == q_init
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is False

    # 3. Rapport REJETE
    cp = terrain["clients"]["CP"]
    rep_rejet = cp.post(
        f"{API}/rapports/{identifiant}/rejeter/",
        {"motif": "Travaux non conformes aux plans prescrits."},
        format="json",
    )
    assert rep_rejet.status_code == 200
    rapport.refresh_from_db()
    assert rapport.statut == StatutRapport.REJETE

    res_rejete = synchroniser_rapport_approuve(identifiant)
    assert res_rejete is False
    activite.refresh_from_db()
    assert activite.quantite_realisee == q_init
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is False


def test_rapport_sans_journal_marque_sans_erreur(terrain):
    """(b.3) Un rapport sans JournalChantier est marqué synchronisé, sans erreur."""
    projet = terrain["projet"]
    user = terrain["CP"]

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=aujourdhui(),
        auteur=user,
        statut=StatutRapport.APPROUVE,
    )

    res = synchroniser_rapport_approuve(rapport.id)
    assert res is True
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is True


def test_ligne_quantite_jour_null_ou_zero_ignoree(terrain):
    """(b.4) Une ligne quantite_jour null ou <= 0 est ignorée."""
    lot = terrain["lot"]
    activite = terrain["activite"]
    projet = terrain["projet"]
    user = terrain["CC"]

    act_null = activite
    act_zero = Activite.objects.create(
        lot=lot, libelle="Béton armé", quantite_prevue=50, unite="M3"
    )
    act_valide = Activite.objects.create(
        lot=lot, libelle="Armatures", quantite_prevue=50, unite="KG"
    )

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=aujourdhui(),
        auteur=user,
        statut=StatutRapport.APPROUVE,
    )
    saisie = {
        "activites": [
            {"activite_id": str(act_null.id), "quantite_jour": None},
            {"activite_id": str(act_zero.id), "quantite_jour": 0},
            {"activite_id": str(act_valide.id), "quantite_jour": 10.0},
        ],
        "production": [],
    }
    JournalChantier.objects.create(rapport=rapport, saisie=saisie)

    res = synchroniser_rapport_approuve(rapport.id)
    assert res is True

    act_null.refresh_from_db()
    act_zero.refresh_from_db()
    act_valide.refresh_from_db()
    rapport.refresh_from_db()

    assert rapport.f3_sync_done is True
    assert act_null.quantite_realisee == Decimal("0.000")
    assert act_zero.quantite_realisee == Decimal("0.000")
    assert act_valide.quantite_realisee == Decimal("10.000")
    assert act_valide.avancement == Decimal("20.00")


def test_cumul_plusieurs_lignes_meme_activite(terrain):
    """Cumul de plusieurs lignes d'une même activité (activités et production)."""
    activite = terrain["activite"]
    projet = terrain["projet"]
    user = terrain["CC"]

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=aujourdhui(),
        auteur=user,
        statut=StatutRapport.APPROUVE,
    )
    saisie = {
        "activites": [
            {"activite_id": str(activite.id), "quantite_jour": 15.0},
            {"activite_id": str(activite.id), "quantite_jour": 5.0},
        ],
        "production": [
            {"activite_id": str(activite.id), "quantite_jour": 10.0, "intervenant": "Tâcheron 1"},
        ],
    }
    JournalChantier.objects.create(rapport=rapport, saisie=saisie)

    res = synchroniser_rapport_approuve(rapport.id)
    assert res is True
    activite.refresh_from_db()
    # 15.0 + 5.0 + 10.0 = 30.0
    assert activite.quantite_realisee == Decimal("30.000")
    assert activite.avancement == Decimal("30.00")


def test_activite_introuvable_ou_supprimee_ignoree(terrain):
    """Une activité introuvable ou supprimée logiquement est ignorée sans erreur."""
    lot = terrain["lot"]
    activite_active = terrain["activite"]
    activite_supprimee = Activite.objects.create(
        lot=lot, libelle="Démolition", quantite_prevue=100, unite="M3"
    )
    activite_supprimee.supprime_le = timezone.now()
    activite_supprimee.save(update_fields=["supprime_le"])

    projet = terrain["projet"]
    user = terrain["CC"]

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=aujourdhui(),
        auteur=user,
        statut=StatutRapport.APPROUVE,
    )
    saisie = {
        "activites": [
            {"activite_id": str(uuid4()), "quantite_jour": 20.0},
            {"activite_id": str(activite_supprimee.id), "quantite_jour": 25.0},
            {"activite_id": str(activite_active.id), "quantite_jour": 8.0},
        ],
        "production": [],
    }
    JournalChantier.objects.create(rapport=rapport, saisie=saisie)

    res = synchroniser_rapport_approuve(rapport.id)
    assert res is True

    activite_active.refresh_from_db()
    activite_supprimee.refresh_from_db()

    assert activite_active.quantite_realisee == Decimal("8.000")
    assert activite_supprimee.quantite_realisee == Decimal("0.000")


def test_declencher_recalcul_sante_appele_une_fois(terrain):
    """(c) declencher_recalcul_sante est appelée une fois avec RAPPORT_APPROBATION."""
    activite = terrain["activite"]
    projet = terrain["projet"]
    user = terrain["CC"]

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=aujourdhui(),
        auteur=user,
        statut=StatutRapport.APPROUVE,
    )
    saisie = {
        "activites": [{"activite_id": str(activite.id), "quantite_jour": 5.0}],
        "production": [],
    }
    JournalChantier.objects.create(rapport=rapport, saisie=saisie)

    with patch("apps.projets.services.avancement.declencher_recalcul_sante") as mock_sante:
        res = synchroniser_rapport_approuve(rapport.id)
        assert res is True
        mock_sante.assert_called_once_with(
            projet_id=projet.id,
            declencheur_type="RAPPORT_APPROBATION",
            declencheur_id=rapport.id,
        )

        # Un second appel ne redéclenche pas le recalcul
        res2 = synchroniser_rapport_approuve(rapport.id)
        assert res2 is False
        mock_sante.assert_called_once()


def test_signal_post_save_sur_rapport_journalier(
    terrain, django_capture_on_commit_callbacks
):
    """Vérifie que la sauvegarde d'un rapport avec statut APPROUVE déclenche le signal."""
    activite = terrain["activite"]
    projet = terrain["projet"]
    user = terrain["CC"]

    rapport = RapportJournalier.objects.create(
        projet=projet,
        date_rapport=aujourdhui(),
        auteur=user,
        statut=StatutRapport.SOUMIS,
    )
    saisie = {
        "activites": [{"activite_id": str(activite.id), "quantite_jour": 7.0}],
        "production": [],
    }
    JournalChantier.objects.create(rapport=rapport, saisie=saisie)

    with django_capture_on_commit_callbacks(execute=True):
        rapport.statut = StatutRapport.APPROUVE
        rapport.save()

    activite.refresh_from_db()
    rapport.refresh_from_db()
    assert rapport.f3_sync_done is True
    assert activite.quantite_realisee == Decimal("7.000")

