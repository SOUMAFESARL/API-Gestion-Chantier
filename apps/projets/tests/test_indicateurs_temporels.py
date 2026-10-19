"""Tests pour les indicateurs temporels calculés à la volée (Tâche T3).

Vérifie :
1. Calcul des fonctions pures avec date_reference explicite (lot et projet).
2. GET /api/v1/projets/{id}/ rend avancement_theorique et delta_retard calculés à l'appel
   et ignore le champ stocké fixé à 99.00.
3. GET /api/v1/projets/{id}/lots/ expose avancement_temporel et delta_retard (nullables).
4. GET /api/v1/tableau-de-bord/ calcule avancement_theorique à l'appel et expose delta_retard.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import (
    ModeExecution,
    RoleGlobal,
    RoleProjet,
    RoleTiersChoix,
    StatutProjet,
    StatutUtilisateur,
    TypeBordereau,
    TypeTiers,
)
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.projets.services.indicateurs_temporels import (
    calendrier_pour_lots,
    calendrier_pour_projets,
    indicateurs_temporels_lot,
    indicateurs_temporels_projet,
)
from apps.tiers.models import RoleTiers, Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Password123!"


# ==============================================================================
# 1. TESTS UNITAIRES DES FONCTIONS AVEC DATE_REFERENCE EXPLICITE
# ==============================================================================

@pytest.mark.django_db
def test_indicateurs_temporels_lot_date_reference_explicite(schema_demo):
    """Un lot avec baseline calcule son avancement temporel avec date_reference explicite."""
    # Semaine du lundi 5 au vendredi 9 octobre 2026 (5 jours ouvrés)
    lot = MagicMock(
        date_debut_baseline=date(2026, 10, 5),
        date_fin_baseline=date(2026, 10, 9),
        date_debut_prevue=None,
        date_fin_prevue=None,
        activites=MagicMock(all=MagicMock(return_value=[])),
        avancement=Decimal("20.0"),
    )

    # Mercredi 7 octobre 2026 : 3 jours écoulés (lun, mar, mer) sur 5 -> 60.0%
    res = indicateurs_temporels_lot(lot, date_reference=date(2026, 10, 7))
    assert res["avancement_temporel"] == 60.0
    # Physique = 20.0 (fallback lot.avancement), delta = 60.0 - 20.0 = 40.0
    assert res["delta_retard"] == 40.0


@pytest.mark.django_db
def test_indicateurs_temporels_lot_sans_dates(schema_demo):
    """Un lot sans dates contractuelles renvoie None pour avancement_temporel et delta."""
    lot = MagicMock(
        date_debut_baseline=None,
        date_fin_baseline=None,
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    res = indicateurs_temporels_lot(lot, date_reference=date(2026, 10, 7))
    assert res["avancement_temporel"] is None
    assert res["delta_retard"] is None


@pytest.mark.django_db
def test_indicateurs_temporels_lot_bornes(schema_demo):
    """Avant le début contractuel -> 0%, après la fin contractuelle -> 100%."""
    lot = MagicMock(
        date_debut_baseline=date(2026, 10, 5),
        date_fin_baseline=date(2026, 10, 9),
        date_debut_prevue=None,
        date_fin_prevue=None,
        activites=MagicMock(all=MagicMock(return_value=[])),
        avancement=Decimal("0.0"),
    )
    # Avant début
    res_avant = indicateurs_temporels_lot(lot, date_reference=date(2026, 10, 1))
    assert res_avant["avancement_temporel"] == 0.0

    # Après fin
    res_apres = indicateurs_temporels_lot(lot, date_reference=date(2026, 10, 15))
    assert res_apres["avancement_temporel"] == 100.0


@pytest.mark.django_db
def test_indicateurs_temporels_projet_date_reference_explicite(schema_demo):
    """Consolidation temporelle d'un projet pondérée par le budget des lots."""
    projet = MagicMock()
    # Lot 1 : budget 600 000, 5 jours ouvrés (5 au 9 oct 2026). À mer 7 oct -> 3/5 = 60%
    lot1 = MagicMock(
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("600000"),
        date_debut_baseline=date(2026, 10, 5),
        date_fin_baseline=date(2026, 10, 9),
        activites=MagicMock(all=MagicMock(return_value=[])),
        avancement=Decimal("0.0"),
    )
    # Lot 2 : budget 400 000, 10 jours ouvrés (5 au 16 oct 2026). À mer 7 oct -> 3/10 = 30%
    lot2 = MagicMock(
        est_actif=True,
        supprime_le=None,
        budget_initial_montant=Decimal("400000"),
        date_debut_baseline=date(2026, 10, 5),
        date_fin_baseline=date(2026, 10, 16),
        activites=MagicMock(all=MagicMock(return_value=[])),
        avancement=Decimal("0.0"),
    )
    projet.lots.all.return_value = [lot1, lot2]

    # Pondération : (60.0 * 600_000 + 30.0 * 400_000) / 1_000_000 = 48.0%
    res = indicateurs_temporels_projet(projet, date_reference=date(2026, 10, 7))
    assert res["avancement_temporel"] == 48.0
    # Physique = 0.0, retard = 48.0 - 0.0 = 48.0
    assert res["delta_retard"] == 48.0


# ==============================================================================
# 2. TESTS D'INTÉGRATION API
# ==============================================================================

@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def dg_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="dg.indicateurs@demo.ci").delete()
        dg = Utilisateur.objects.create_user(
            email="dg.indicateurs@demo.ci",
            nom="Directeur",
            prenom="Général",
            password=MOT_DE_PASSE,
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )
        yield dg


@pytest.fixture
def projet_avec_lot_budgete(db, dg_user):
    with schema_context(SCHEMA):
        # Création client
        client_moa = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="Client Test Indicateurs",
            telephone="+2250102030405",
        )
        RoleTiers.objects.create(tiers=client_moa, role=RoleTiersChoix.CLIENT_MOA)

        today = timezone.localdate()
        # Projet avec champ stocké forcé à 99.00 pour prouver qu'il n'est plus lu
        projet = Projet.objects.create(
            reference="PRJ-IND-001",
            nom="Chantier Indicateurs Temporels",
            client=client_moa,
            chef_projet=dg_user,
            ville="Abidjan",
            budget_initial_montant=1_000_000_000,
            date_debut_prevue=today - timedelta(days=20),
            date_fin_prevue=today + timedelta(days=20),
            avancement_reel=Decimal("25.00"),
            avancement_theorique=Decimal("99.00"),  # Doit être ignoré à la lecture
            statut=StatutProjet.EN_COURS,
        )

        # Lot budgété et daté autour d'aujourd'hui
        lot = Lot.objects.create(
            projet=projet,
            code="LOT-01",
            libelle="Lot Gros Œuvre",
            mode_execution=ModeExecution.REGIE,
            type_bordereau=TypeBordereau.FORFAIT,
            budget_initial_montant=500_000_000,
            date_debut_baseline=today - timedelta(days=10),
            date_fin_baseline=today + timedelta(days=10),
            ordre=1,
            avancement=Decimal("25.00"),
        )

        # Lot sans dates (pour vérifier les nullables)
        lot_sans_dates = Lot.objects.create(
            projet=projet,
            code="LOT-02",
            libelle="Lot Finitions",
            mode_execution=ModeExecution.SOUS_TRAITANCE_STRUCTUREE,
            type_bordereau=TypeBordereau.PRIX_UNITAIRE,
            budget_initial_montant=200_000_000,
            date_debut_prevue=None,
            date_fin_prevue=None,
            ordre=2,
        )

        AffectationProjet.objects.create(
            projet=projet,
            utilisateur=dg_user,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        )

        yield {
            "projet": projet,
            "lot": lot,
            "lot_sans_dates": lot_sans_dates,
        }


@pytest.mark.django_db
def test_api_detail_projet_avancement_temporel_calcule(
    client_tenant, dg_user, projet_avec_lot_budgete
):
    """Le détail d'un projet rend avancement_theorique = avancement temporel calculé à l'appel

    (et non le champ stocké fixé à 99.00), plus le champ delta_retard.
    """
    client_tenant.force_authenticate(user=dg_user)
    projet = projet_avec_lot_budgete["projet"]

    url = f"/api/v1/projets/{projet.id}/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    indics = indicateurs_temporels_projet(projet)

    # La valeur retournée est l'avancement calculé à l'appel
    assert data["avancement_theorique"] == indics["avancement_temporel"]
    # Preuve que le champ stocké à 99.00 est ignoré
    assert data["avancement_theorique"] != 99.0
    assert data["avancement_theorique"] != 99
    # delta_retard est bien exposé
    assert "delta_retard" in data
    assert data["delta_retard"] == indics["delta_retard"]


@pytest.mark.django_db
def test_api_liste_lots_expose_indicateurs_temporels(
    client_tenant, dg_user, projet_avec_lot_budgete
):
    """La liste des lots expose avancement_temporel et delta_retard (nullables)."""
    client_tenant.force_authenticate(user=dg_user)
    projet = projet_avec_lot_budgete["projet"]
    lot_avec_dates = projet_avec_lot_budgete["lot"]

    url = f"/api/v1/projets/{projet.id}/lots/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) >= 2

    lots_par_code = {item["code"]: item for item in data}

    # Lot 1 (avec dates)
    item_lot1 = lots_par_code["LOT-01"]
    assert "avancement_temporel" in item_lot1
    assert "delta_retard" in item_lot1
    indics_lot1 = indicateurs_temporels_lot(lot_avec_dates)
    assert item_lot1["avancement_temporel"] == indics_lot1["avancement_temporel"]
    assert item_lot1["delta_retard"] == indics_lot1["delta_retard"]

    # Lot 2 (sans dates -> nullables)
    item_lot2 = lots_par_code["LOT-02"]
    assert "avancement_temporel" in item_lot2
    assert "delta_retard" in item_lot2
    assert item_lot2["avancement_temporel"] is None
    assert item_lot2["delta_retard"] is None


@pytest.mark.django_db
def test_api_tableau_de_bord_rend_avancement_temporel_et_delta(
    client_tenant, dg_user, projet_avec_lot_budgete
):
    """Le portefeuille du tableau de bord calcule theorique à l'appel et expose delta_retard."""
    client_tenant.force_authenticate(user=dg_user)
    projet = projet_avec_lot_budgete["projet"]

    url = "/api/v1/tableau-de-bord/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    projets_portefeuille = data["projets"]
    item_projet = next((p for p in projets_portefeuille if p["id"] == str(projet.id)), None)
    assert item_projet is not None

    indics = indicateurs_temporels_projet(projet)

    # theorique vient de indicateurs_temporels_projet
    assert item_projet["avancement_theorique"] != 99.0
    assert item_projet["avancement_theorique"] != 99
    assert item_projet["avancement_theorique"] == indics["avancement_temporel"]

    # delta_retard est présent et conforme
    assert "delta_retard" in item_projet
    assert item_projet["delta_retard"] == indics["delta_retard"]

    # ecart reste (réel - théorique), arrondi à 1 décimale par la vue (le serializer
    # du tableau de bord ne sert qu'à la documentation OpenAPI : il ne convertit rien).
    ecart_attendu = round(float(projet.avancement_reel or 0) - indics["avancement_temporel"], 1)
    assert item_projet["ecart"] == ecart_attendu


# ==============================================================================
# 3. TESTS DU CALENDRIER MULTI-OBJETS
# ==============================================================================

@pytest.mark.django_db
def test_calendrier_pour_projets_bornes(schema_demo):
    """calendrier_pour_projets instancie un calendrier couvrant tous les projets."""
    p1 = MagicMock(
        date_debut_baseline=date(2026, 1, 1),
        date_fin_baseline=date(2026, 3, 1),
        date_debut_prevue=None,
        date_fin_prevue=None,
        lots=MagicMock(all=MagicMock(return_value=[])),
    )
    p2 = MagicMock(
        date_debut_baseline=date(2026, 2, 1),
        date_fin_baseline=date(2026, 6, 1),
        date_debut_prevue=None,
        date_fin_prevue=None,
        lots=MagicMock(all=MagicMock(return_value=[])),
    )
    cal = calendrier_pour_projets([p1, p2], date_reference=date(2026, 4, 1))
    assert cal is not None


@pytest.mark.django_db
def test_calendrier_pour_lots_bornes(schema_demo):
    """calendrier_pour_lots instancie un calendrier couvrant tous les lots."""
    l1 = MagicMock(
        date_debut_baseline=date(2026, 1, 1),
        date_fin_baseline=date(2026, 3, 1),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    l2 = MagicMock(
        date_debut_baseline=date(2026, 2, 1),
        date_fin_baseline=date(2026, 6, 1),
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    cal = calendrier_pour_lots([l1, l2], date_reference=date(2026, 4, 1))
    assert cal is not None

