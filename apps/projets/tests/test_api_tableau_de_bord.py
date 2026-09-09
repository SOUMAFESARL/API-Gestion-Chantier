"""Tests pour l'endpoint GET /api/v1/tableau-de-bord/."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleTiersChoix, StatutUtilisateur, TypeTiers
from apps.projets.models import Projet
from apps.tiers.models import RoleTiers, Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="cp.dashboard@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="cp.dashboard@demo.ci",
            password="MotDePasse1!",
            nom="Konan",
            prenom="Yao",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        yield admin


@pytest.mark.django_db
def test_consulter_tableau_de_bord(client_tenant, admin_user):
    """Un utilisateur authentifié reçoit la synthèse de pilotage BTP."""
    client_tenant.force_authenticate(user=admin_user)

    with schema_context(SCHEMA):
        # Créer un tiers et un projet
        client_moa = Tiers.objects.create(
            raison_sociale="Ministère de la Construction",
            telephone="+22507070707",
            type_tiers=TypeTiers.ENTREPRISE,
        )
        RoleTiers.objects.create(tiers=client_moa, role=RoleTiersChoix.CLIENT_MOA)

        Projet.objects.create(
            reference="PRJ-2026-001",
            nom="Résidence Cocody",
            client=client_moa,
            chef_projet=admin_user,
            ville="Abidjan",
            budget_initial_montant=875_000_000_00,
            date_debut_prevue="2026-09-01",
            date_fin_prevue="2027-06-30",
            avancement_reel=34.00,
            avancement_theorique=32.00,
            indice_sante=92,
        )

    url = "/api/v1/tableau-de-bord/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "metriques" in data
    assert data["metriques"]["chantiers_actifs"] >= 1
    assert data["metriques"]["sante_globale"] > 0
    assert "projets" in data
    assert len(data["projets"]) >= 1
    p = data["projets"][0]
    assert p["nom"] == "Résidence Cocody"
    assert p["avancement_reel"] == 34.0
    assert p["avancement_theorique"] == 32.0
    assert "bons_paiement_a_valider" in data
    assert "meteo" in data
    assert data["aucun_chantier"] is False


@pytest.mark.django_db
def test_tableau_de_bord_vide_aucun_chantier(client_tenant, admin_user):
    """REC-S1-04-A : Quand 0 chantier existe,
    GET /tableau-de-bord/ renvoie aucun_chantier: True et métriques à zéro.
    """
    client_tenant.force_authenticate(user=admin_user)

    with schema_context(SCHEMA):
        Projet.objects.all().delete()

    url = "/api/v1/tableau-de-bord/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["aucun_chantier"] is True
    assert data["metriques"]["chantiers_actifs"] == 0
    assert data["metriques"]["budget_total_montant"] == 0
    assert data["metriques"]["budget_engage_montant"] == 0
    assert data["projets"] == []
    assert data["bons_paiement_a_valider"] == []
