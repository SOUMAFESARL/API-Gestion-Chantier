"""Tests unitaires et d'intégration pour la machine à états et l'évaluation quotidienne.

Vérifie :
1. Transitions strictement calendaires (PLANIFIE -> EN_COURS -> EN_RETARD).
2. Rétablissement instantané en temps réel après décalage justifié (US-033 / RG-11).
3. Verrou d'intégrité de réception (100% lots clôturés).
4. Commande d'évaluation quotidienne multi-tenant et tâche Celery.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutActivite,
    StatutLot,
    StatutProjet,
    StatutUtilisateur,
)
from apps.projets.models import (
    Activite,
    AffectationProjet,
    Lot,
    MotifReport,
    Projet,
)
from apps.projets.services.machine_etats import (
    evaluer_statut_activite,
    evaluer_statut_lot,
    evaluer_statut_projet,
    executer_evaluation_quotidienne_schema,
    retablir_statut_apres_decalage_si_necessaire,
    valider_transition_reception,
)
from apps.projets.services.reprogrammation import reprogrammer_date_instance
from apps.projets.tasks import evaluer_statuts_quotidiens_tous_tenants
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db


@pytest.fixture
def environnement_machine_etats(schema_demo):
    """Initialise un projet, des lots, des activités et des utilisateurs de test."""
    admin = Utilisateur.objects.create_user(
        email="admin.etats@demo.ci",
        password="Test12345!",
        nom="Admin Machine",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    cp = Utilisateur.objects.create_user(
        email="cp.etats@demo.ci",
        password="Test12345!",
        nom="Chef Projet",
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    client_tiers = Tiers.objects.create(raison_sociale="Client Immo Test", type_tiers="ENTREPRISE")

    motif = MotifReport.objects.create(
        code="INTEMPERIES_SEVERES",
        libelle="Intempéries et fortes pluies exceptionnelles",
        est_actif=True,
    )

    aujourdhui = timezone.now().date()

    projet = Projet.objects.create(
        reference="PRJ-MACHINE-01",
        nom="Chantier Machine Test",
        client=client_tiers,
        ville="Abidjan",
        maitre_ouvrage="SCI Test",
        chef_projet=cp,
        date_debut_prevue=aujourdhui + timedelta(days=2),
        date_fin_prevue=aujourdhui + timedelta(days=30),
        statut=StatutProjet.EN_ATTENTE,
    )

    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=cp,
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
    )

    lot1 = Lot.objects.create(
        projet=projet,
        code="LOT-01",
        libelle="Terrassement & Fondations",
        date_debut_prevue=aujourdhui + timedelta(days=2),
        date_fin_prevue=aujourdhui + timedelta(days=10),
        statut=StatutLot.PLANIFIE,
        avancement=Decimal("0.00"),
    )

    lot2 = Lot.objects.create(
        projet=projet,
        code="LOT-02",
        libelle="Gros Œuvre",
        date_debut_prevue=aujourdhui + timedelta(days=11),
        date_fin_prevue=aujourdhui + timedelta(days=28),
        statut=StatutLot.PLANIFIE,
        avancement=Decimal("0.00"),
    )

    act1 = Activite.objects.create(
        lot=lot1,
        libelle="Fouilles en pleine masse",
        quantite_prevue=Decimal("100.000"),
        quantite_realisee=Decimal("0.000"),
        avancement=Decimal("0.00"),
        date_debut_prevue=aujourdhui + timedelta(days=2),
        date_fin_prevue=aujourdhui + timedelta(days=5),
        statut=StatutActivite.PLANIFIE,
    )

    client_api = APIClient(HTTP_HOST="demo.localhost")
    client_api.force_authenticate(admin)

    return {
        "admin": admin,
        "cp": cp,
        "motif": motif,
        "projet": projet,
        "lot1": lot1,
        "lot2": lot2,
        "act1": act1,
        "client": client_api,
        "aujourdhui": aujourdhui,
    }


def test_transition_calendaire_projet(environnement_machine_etats):
    """Vérifie le cycle calendaire d'un projet : EN_ATTENTE -> EN_COURS -> EN_RETARD."""
    env = environnement_machine_etats
    projet = env["projet"]
    j = env["aujourdhui"]

    # 1. Avant la date de début : reste EN_ATTENTE
    change = evaluer_statut_projet(projet, date_reference=j)
    assert not change
    assert projet.statut == StatutProjet.EN_ATTENTE

    # 2. Au jour J de début : bascule strictement calendaire à EN_COURS
    change = evaluer_statut_projet(projet, date_reference=projet.date_debut_prevue)
    assert change
    assert projet.statut == StatutProjet.EN_COURS

    # 3. Après la date de fin : bascule automatique à EN_RETARD
    apres_fin = projet.date_fin_prevue + timedelta(days=1)
    change = evaluer_statut_projet(projet, date_reference=apres_fin)
    assert change
    assert projet.statut == StatutProjet.EN_RETARD

    # 4. Statut manuel SUSPENDU : préservé (non écrasé par la tâche calendaire)
    projet.statut = StatutProjet.SUSPENDU
    projet.save(update_fields=["statut"])
    change = evaluer_statut_projet(projet, date_reference=apres_fin)
    assert not change
    assert projet.statut == StatutProjet.SUSPENDU


def test_transition_calendaire_activite_et_lot(environnement_machine_etats):
    """Vérifie les transitions calendaires des activités et l'agrégation sur le lot."""
    env = environnement_machine_etats
    act1 = env["act1"]
    lot1 = env["lot1"]

    # 1. Activité démarre à sa date de début
    evaluer_statut_activite(act1, date_reference=act1.date_debut_prevue)
    assert act1.statut == StatutActivite.EN_COURS

    # 2. Dépassement de date fin -> EN_RETARD
    evaluer_statut_activite(act1, date_reference=act1.date_fin_prevue + timedelta(days=1))
    assert act1.statut == StatutActivite.EN_RETARD

    # 3. Achèvement à 100% -> CLOTURE
    act1.avancement = Decimal("100.00")
    evaluer_statut_activite(act1)
    assert act1.statut == StatutActivite.CLOTURE

    # 4. Le lot dont 100% des activités sont clôturées passe à CLOTURE
    evaluer_statut_lot(lot1)
    assert lot1.statut == StatutLot.CLOTURE


def test_retablissement_instantane_temps_reel(environnement_machine_etats):
    """Vérifie qu'un décalage justifié rétablit immédiatement EN_RETARD -> EN_COURS."""
    env = environnement_machine_etats
    projet = env["projet"]
    motif = env["motif"]
    j = env["aujourdhui"]

    # On simule un projet en retard
    projet.date_debut_prevue = j - timedelta(days=20)
    projet.date_fin_prevue = j - timedelta(days=5)
    projet.statut = StatutProjet.EN_RETARD
    projet.save(update_fields=["date_debut_prevue", "date_fin_prevue", "statut"])

    # Reprogrammation avec nouvelle date de fin dans le futur (après tous les lots) et justification >= 30 car
    nouvelle_fin = j + timedelta(days=35)
    resultat = reprogrammer_date_instance(
        instance=projet,
        nouvelle_date_fin=nouvelle_fin,
        motif_id=str(motif.id),
        justification="Avenant numéro 1 signé avec le client suite aux intempéries majeures.",
        auteur=env["admin"],
    )

    projet.refresh_from_db()
    assert resultat["statut_retabli"] is True
    assert projet.statut == StatutProjet.EN_COURS
    assert projet.date_fin_prevue == nouvelle_fin


def test_verrou_reception_bloque_si_lots_non_clotures(environnement_machine_etats):
    """L'API refuse catégoriquement (HTTP 400) la réception si des lots ne sont pas clôturés."""
    env = environnement_machine_etats
    projet = env["projet"]
    client = env["client"]

    # Lot 1 à 100% (CLOTURE), Lot 2 à 40% (EN_COURS)
    env["lot1"].statut = StatutLot.CLOTURE
    env["lot1"].avancement = Decimal("100.00")
    env["lot1"].save()

    env["lot2"].statut = StatutLot.EN_COURS
    env["lot2"].avancement = Decimal("40.00")
    env["lot2"].save()

    # Tentative via service
    with pytest.raises(ValidationError) as exc_info:
        valider_transition_reception(projet)
    assert "LOT-02" in str(exc_info.value)

    # Tentative via API PATCH /api/v1/projets/<id>/
    url = f"/api/v1/projets/{projet.id}/"
    response = client.patch(url, {"statut": StatutProjet.RECEPTIONNE}, format="json")
    assert response.status_code == 400
    assert "100 % des lots doivent être clôturés" in str(response.data)
    assert "LOT-02" in str(response.data)


def test_verrou_reception_autorise_si_tous_lots_clotures(environnement_machine_etats):
    """L'API autorise la réception dès que 100 % des lots sont clôturés."""
    env = environnement_machine_etats
    projet = env["projet"]
    client = env["client"]

    # Clôture de tous les lots
    env["lot1"].statut = StatutLot.CLOTURE
    env["lot1"].avancement = Decimal("100.00")
    env["lot1"].save()

    env["lot2"].statut = StatutLot.CLOTURE
    env["lot2"].avancement = Decimal("100.00")
    env["lot2"].save()

    url = f"/api/v1/projets/{projet.id}/"
    response = client.patch(url, {"statut": StatutProjet.RECEPTIONNE}, format="json")
    assert response.status_code == 200, response.data
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.RECEPTIONNE


def test_commande_management_et_tache_celery(environnement_machine_etats):
    """Vérifie l'exécution de la commande d'évaluation quotidienne et de la tâche Celery."""
    env = environnement_machine_etats
    projet = env["projet"]
    j = env["aujourdhui"]

    # Projet planifié pour démarrer aujourd'hui
    projet.date_debut_prevue = j
    projet.save(update_fields=["date_debut_prevue"])

    # Exécution de la commande Django
    call_command("evaluer_statuts_quotidiens", schema="demo")
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_COURS

    # Exécution de la tâche Celery
    rapport = evaluer_statuts_quotidiens_tous_tenants()
    assert "demo" in rapport
    assert "projets_modifies" in rapport["demo"]
