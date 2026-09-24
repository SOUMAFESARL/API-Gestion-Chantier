"""Tests pour les endpoints d'indicateurs de la plateforme Super Admin (/api/v1/indicateurs/)."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Plan
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.tenants.models import Entreprise

HOTE_PLATEFORME = "localhost"


@pytest.fixture(autouse=True)
def autoriser_ip_locale(settings):
    """Autorise l'adresse IP de test dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]


@pytest.fixture
def superuser_admin(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superadmin.dash@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="superadmin.dash@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Admin",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_staff=True,
            is_superuser=True,
        )


@pytest.fixture
def user_standard(db):
    """Crée un utilisateur sans droits Super Admin."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="user.standard@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="user.standard@ccd-digital.ci",
            password="StandardPassword123!",
            nom="Standard",
            prenom="User",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
            is_staff=False,
            is_superuser=False,
        )


@pytest.fixture
def client_api():
    return APIClient(headers={"host": HOTE_PLATEFORME})


@pytest.fixture
def donnees_entreprises(db):
    """Crée des entreprises et abonnements de test dans le schéma public sans toucher demo."""
    with schema_context(get_public_schema_name()):
        # Nettoyer uniquement les tenants de test spécifiques
        test_schemas = ["tenant_alpha", "tenant_beta", "tenant_gamma"]
        Entreprise.objects.filter(schema_name__in=test_schemas).delete()

        plan_pro, _ = Plan.objects.get_or_create(
            code=Plan.Code.MAITRE_OEUVRE,
            defaults={
                "libelle": "Maître d'Œuvre",
                "prix_mensuel_montant": 150_000_00,  # 150 000 FCFA
            },
        )

        # 1. Entreprise active avec abonnement actif
        e1 = Entreprise(
            schema_name="tenant_alpha",
            raison_sociale="Alpha Construction",
            email_contact="contact@alpha.ci",
            statut=StatutEntreprise.ACTIF,
        )
        e1.auto_create_schema = False
        e1.save()
        Abonnement.objects.create(
            entreprise=e1,
            plan=plan_pro,
            date_debut="2026-01-01",
            date_fin="2026-12-31",
            statut=Abonnement.Statut.ACTIF,
            renouvellement_auto=True,
        )

        # 2. Entreprise en essai
        e2 = Entreprise(
            schema_name="tenant_beta",
            raison_sociale="Beta BTP",
            email_contact="contact@beta.ci",
            statut=StatutEntreprise.ESSAI,
        )
        e2.auto_create_schema = False
        e2.save()
        Abonnement.objects.create(
            entreprise=e2,
            plan=plan_pro,
            date_debut="2026-09-10",
            date_fin="2026-09-24",
            fin_essai="2026-09-24",
            statut=Abonnement.Statut.ESSAI,
            renouvellement_auto=True,
        )

        # 3. Entreprise avec impayé
        e3 = Entreprise(
            schema_name="tenant_gamma",
            raison_sociale="Gamma TP",
            email_contact="contact@gamma.ci",
            statut=StatutEntreprise.ACTIF,
        )
        e3.auto_create_schema = False
        e3.save()
        Abonnement.objects.create(
            entreprise=e3,
            plan=plan_pro,
            date_debut="2026-01-01",
            date_fin="2026-06-30",
            statut=Abonnement.Statut.IMPAYE,
            renouvellement_auto=False,
        )

        return e1, e2, e3


@pytest.mark.django_db
def test_acces_refuse_anonyme(client_api):
    """Un utilisateur non authentifié reçoit 401."""
    res = client_api.get("/api/v1/indicateurs/")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_acces_refuse_utilisateur_standard(client_api, user_standard):
    """Un utilisateur sans prérogatives Super Admin reçoit 403."""
    client_api.force_authenticate(user=user_standard)
    res = client_api.get("/api/v1/indicateurs/")
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_indicateurs_plateforme(client_api, superuser_admin, donnees_entreprises):
    """Le Super Admin reçoit les KPIs consolidés corrects."""
    client_api.force_authenticate(user=superuser_admin)
    res = client_api.get("/api/v1/indicateurs/")

    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["nb_clients"] >= 3
    assert data["nb_clients_actifs"] >= 2
    assert data["nb_clients_en_essai"] >= 1
    assert data["nb_clients_impayes"] >= 1
    assert data["revenu_mensuel_centimes"] >= 150_000_00


@pytest.mark.django_db
def test_tendances_indicateurs(client_api, superuser_admin, donnees_entreprises):
    """L'endpoint des tendances renvoie les séries sparklines pour les 5 indicateurs."""
    client_api.force_authenticate(user=superuser_admin)
    res = client_api.get("/api/v1/indicateurs/tendances/")

    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 5

    cles = {item["cle"] for item in data}
    assert cles == {
        "nb_clients",
        "nb_clients_actifs",
        "nb_clients_en_essai",
        "nb_clients_impayes",
        "revenu_mensuel_centimes",
    }

    for item in data:
        assert len(item["points"]) == 5
        assert isinstance(item["variation_pourcent"], int)


@pytest.mark.django_db
def test_evolution_abonnements(client_api, superuser_admin, donnees_entreprises):
    """L'endpoint de l'évolution renvoie 90 points journaliers."""
    client_api.force_authenticate(user=superuser_admin)
    res = client_api.get("/api/v1/indicateurs/evolution/")

    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 90
    assert "date" in data[0]
    assert "renouveles" in data[0]
    assert "non_renouveles" in data[0]
