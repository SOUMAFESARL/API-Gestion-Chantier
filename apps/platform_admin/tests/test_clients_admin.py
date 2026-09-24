"""Tests pour les endpoints de consultation de fiche client et d'actions Super Admin.

Valide :
- GET /api/v1/clients/ : Liste consolidée des entreprises avec abonnements et compteurs.
- GET /api/v1/clients/{id}/ : Fiche détaillée de l'entreprise avec compteurs dynamiques.
- POST /api/v1/clients/{id}/suspendre/ : Suspension avec motif, statut SUSPENDU, trace audit.
- POST /api/v1/clients/{id}/reactiver/ : Réactivation, passage statut ACTIF, trace audit.
- PATCH /api/v1/clients/{id}/abonnement/ : Modification du forfait BTP, trace audit.
- Contrôles d'accès Super Admin (401 / 403) et règles de gestion (404, 409, 422).
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Plan
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import Entreprise

SCHEMA_CLIENT = "demo"
HOTE_PLATEFORME = "localhost"


@pytest.fixture(autouse=True)
def autoriser_ip_locale(settings):
    """Autorise l'adresse IP de test dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]


@pytest.fixture
def super_admin_user(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superadmin.clients@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="superadmin.clients@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Super",
            prenom="Admin",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_staff=True,
            is_superuser=True,
        )


@pytest.fixture
def utilisateur_standard(db):
    """Crée un utilisateur non super-admin dans le schéma tenant."""
    with schema_context(SCHEMA_CLIENT):
        Utilisateur.tous_objets.filter(email="standard@demo.ci").delete()
        return Utilisateur.objects.create_user(
            email="standard@demo.ci",
            password="Password123!",
            nom="Standard",
            prenom="User",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )


@pytest.fixture
def entreprise_test(db):
    """Prépare l'entreprise cliente demo avec les plans BTP et un abonnement actif."""
    with schema_context(get_public_schema_name()):
        p1, _ = Plan.objects.get_or_create(
            code=Plan.Code.BATISSEUR,
            defaults={
                "libelle": "Bâtisseur",
                "prix_mensuel_montant": 19_000_00,
                "limite_projets": 3,
                "limite_utilisateurs": 5,
            },
        )
        Plan.objects.get_or_create(
            code=Plan.Code.MAITRE_OEUVRE,
            defaults={
                "libelle": "Maître d'Œuvre",
                "prix_mensuel_montant": 49_000_00,
                "limite_projets": 50,
                "limite_utilisateurs": 25,
            },
        )
        Plan.objects.get_or_create(
            code=Plan.Code.PROMOTEUR,
            defaults={
                "libelle": "Promoteur",
                "prix_mensuel_montant": 119_000_00,
                "limite_projets": None,
                "limite_utilisateurs": None,
            },
        )

        ent = Entreprise.objects.get(schema_name=SCHEMA_CLIENT)
        ent.statut = StatutEntreprise.ACTIF
        ent.raison_sociale = "Demo Construction SARL"
        ent.nom_commercial = "Demo BTP"
        ent.ville = "Abidjan"
        ent.pays = "CI"
        ent.email_contact = "contact@demo.ci"
        ent.telephone_contact = "+2250102030405"
        ent.save()

        # Associer un abonnement
        ent.abonnements.all().delete()
        aujourdhui = timezone.now().date()
        Abonnement.objects.create(
            entreprise=ent,
            plan=p1,
            date_debut=aujourdhui - timedelta(days=30),
            date_fin=aujourdhui + timedelta(days=335),
            fin_essai=None,
            statut=Abonnement.Statut.ACTIF,
            renouvellement_auto=True,
        )
    return ent


@pytest.fixture
def client_api():
    """Client API configuré sur le domaine de la plateforme."""
    return APIClient(headers={"host": HOTE_PLATEFORME})


# --------------------------------------------------------------------------
# Tests de Consultation (Liste & Fiche Détail)
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_lister_clients_succes(client_api, super_admin_user, entreprise_test):
    """Vérifie que le Super Admin peut lister les entreprises avec leur abonnement et métriques."""
    client_api.force_authenticate(user=super_admin_user)

    url = "/api/v1/admins/clients/"
    reponse = client_api.get(url)

    assert reponse.status_code == status.HTTP_200_OK
    donnees = reponse.json()
    assert isinstance(donnees, list)
    assert len(donnees) >= 1

    trouve = next((c for c in donnees if c["id"] == str(entreprise_test.id)), None)
    assert trouve is not None
    assert trouve["raison_sociale"] == "Demo Construction SARL"
    assert trouve["nom_commercial"] == "Demo BTP"
    assert trouve["slug"] == SCHEMA_CLIENT
    assert trouve["statut"] == "ACTIF"
    assert trouve["nb_projets"] >= 0
    assert "abonnement" in trouve
    assert trouve["abonnement"]["statut"] == "ACTIF"
    assert trouve["abonnement"]["plan_code"] == "BATISSEUR"
    assert trouve["abonnement"]["montant_mensuel_centimes"] == 19_000_00


@pytest.mark.django_db
def test_lister_clients_recherche_succes(client_api, super_admin_user, entreprise_test):
    """Vérifie le filtrage par mot-clé dans la liste des clients."""
    client_api.force_authenticate(user=super_admin_user)

    # Recherche fructueuse
    reponse = client_api.get("/api/v1/admins/clients/?recherche=Construction")
    assert reponse.status_code == status.HTTP_200_OK
    donnees = reponse.json()
    assert any(c["id"] == str(entreprise_test.id) for c in donnees)

    # Recherche infructueuse
    reponse_vide = client_api.get("/api/v1/admins/clients/?recherche=Introuvable999XYZ")
    assert reponse_vide.status_code == status.HTTP_200_OK
    donnees_vides = reponse_vide.json()
    assert len(donnees_vides) == 0


@pytest.mark.django_db
def test_lister_clients_refus_si_non_super_admin(client_api, utilisateur_standard):
    """Vérifie qu'un utilisateur non-staff ne peut pas lister les clients de la plateforme."""
    client_api.force_authenticate(user=utilisateur_standard)
    reponse = client_api.get("/api/v1/admins/clients/")
    assert reponse.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_fiche_client_succes(client_api, super_admin_user, entreprise_test):
    """Vérifie que la fiche détail retourne toutes les données requises par le frontend."""
    client_api.force_authenticate(user=super_admin_user)

    url = f"/api/v1/admins/clients/{entreprise_test.id}/"
    reponse = client_api.get(url)

    assert reponse.status_code == status.HTTP_200_OK
    client = reponse.json()

    assert client["id"] == str(entreprise_test.id)
    assert client["raison_sociale"] == "Demo Construction SARL"
    assert client["nom_commercial"] == "Demo BTP"
    assert client["slug"] == SCHEMA_CLIENT
    assert client["pays"] == "CI"
    assert client["ville"] == "Abidjan"
    assert client["email_contact"] == "contact@demo.ci"
    assert client["telephone_contact"] == "+2250102030405"
    assert client["statut"] == "ACTIF"
    assert "cree_le" in client
    assert "nb_utilisateurs" in client
    assert client["nb_projets"] >= 0

    abo = client["abonnement"]
    assert abo["statut"] == "ACTIF"
    assert abo["plan_code"] == "BATISSEUR"
    assert abo["montant_mensuel_centimes"] == 19_000_00
    assert abo["renouvellement_auto"] is True


@pytest.mark.django_db
def test_fiche_client_introuvable_404(client_api, super_admin_user):
    """Vérifie qu'un UUID inexistant renvoie une erreur 404 introuvable."""
    client_api.force_authenticate(user=super_admin_user)

    fake_id = uuid.uuid4()
    reponse = client_api.get(f"/api/v1/admins/clients/{fake_id}/")

    assert reponse.status_code == status.HTTP_404_NOT_FOUND


# --------------------------------------------------------------------------
# Tests d'Actions Administrateur (Suspension, Réactivation, Plan)
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_suspendre_client_succes_et_audit(client_api, super_admin_user, entreprise_test):
    """Vérifie la suspension complète du client avec motif et trace d'audit."""
    client_api.force_authenticate(user=super_admin_user)

    url = f"/api/v1/admins/clients/{entreprise_test.id}/suspendre/"
    payload = {"motif": "Facture impayée depuis plus de 30 jours."}

    reponse = client_api.post(url, data=payload, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    client = reponse.json()
    assert client["statut"] == "SUSPENDU"
    assert client["abonnement"]["statut"] == "SUSPENDU"
    assert client["abonnement"]["renouvellement_auto"] is False

    # Vérification en base de données
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(id=entreprise_test.id)
        assert ent.statut == StatutEntreprise.SUSPENDU

        abo = ent.abonnements.first()
        assert abo.statut == Abonnement.Statut.SUSPENDU
        assert abo.renouvellement_auto is False

        # Vérification du journal de plateforme
        entree_audit = JournalPlateforme.objects.filter(
            entreprise_id=entreprise_test.id, action="SUSPENSION_CLIENT"
        ).first()
        assert entree_audit is not None
        assert entree_audit.utilisateur_id == super_admin_user.id
        assert entree_audit.detail["motif"] == "Facture impayée depuis plus de 30 jours."


@pytest.mark.django_db
def test_suspendre_client_deja_suspendu_409(client_api, super_admin_user, entreprise_test):
    """Vérifie qu'une seconde tentative de suspension renvoie 409 Conflit."""
    with schema_context(get_public_schema_name()):
        entreprise_test.statut = StatutEntreprise.SUSPENDU
        entreprise_test.save()

    client_api.force_authenticate(user=super_admin_user)
    url = f"/api/v1/admins/clients/{entreprise_test.id}/suspendre/"
    reponse = client_api.post(url, data={"motif": "Nouveau motif"}, format="json")

    assert reponse.status_code == status.HTTP_409_CONFLICT


@pytest.mark.django_db
def test_suspendre_client_motif_obligatoire_400(client_api, super_admin_user, entreprise_test):
    """Vérifie que l'absence de motif est refusée avec 400 Bad Request."""
    client_api.force_authenticate(user=super_admin_user)
    url = f"/api/v1/admins/clients/{entreprise_test.id}/suspendre/"

    # Payload vide
    reponse = client_api.post(url, data={}, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST

    # Motif trop court
    reponse = client_api.post(url, data={"motif": "ab"}, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_reactiver_client_succes_et_audit(client_api, super_admin_user, entreprise_test):
    """Vérifie la réactivation d'un client suspendu et sa traçabilité."""
    with schema_context(get_public_schema_name()):
        entreprise_test.statut = StatutEntreprise.SUSPENDU
        entreprise_test.save()
        abo = entreprise_test.abonnements.first()
        abo.statut = Abonnement.Statut.SUSPENDU
        abo.save()

    client_api.force_authenticate(user=super_admin_user)
    url = f"/api/v1/admins/clients/{entreprise_test.id}/reactiver/"
    reponse = client_api.post(url, data={}, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    client = reponse.json()
    assert client["statut"] == "ACTIF"
    assert client["abonnement"]["statut"] == "ACTIF"
    assert client["abonnement"]["renouvellement_auto"] is True

    # Vérification en base de données
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(id=entreprise_test.id)
        assert ent.statut == StatutEntreprise.ACTIF

        entree_audit = JournalPlateforme.objects.filter(
            entreprise_id=entreprise_test.id, action="REACTIVATION_CLIENT"
        ).first()
        assert entree_audit is not None
        assert entree_audit.action == "REACTIVATION_CLIENT"


@pytest.mark.django_db
def test_reactiver_client_non_suspendu_409(client_api, super_admin_user, entreprise_test):
    """Vérifie qu'un client déjà ACTIF ne peut pas être réactivé (409 Conflit)."""
    client_api.force_authenticate(user=super_admin_user)
    url = f"/api/v1/admins/clients/{entreprise_test.id}/reactiver/"
    reponse = client_api.post(url, data={}, format="json")

    assert reponse.status_code == status.HTTP_409_CONFLICT


@pytest.mark.django_db
def test_changer_plan_client_succes_et_audit(client_api, super_admin_user, entreprise_test):
    """Vérifie le changement de plan d'un client avec mise à jour du tarif et traçabilité."""
    client_api.force_authenticate(user=super_admin_user)

    url = f"/api/v1/admins/clients/{entreprise_test.id}/abonnement/"
    payload = {"plan_code": "PROMOTEUR"}

    reponse = client_api.patch(url, data=payload, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    client = reponse.json()
    assert client["abonnement"]["plan_code"] == "PROMOTEUR"
    assert client["abonnement"]["montant_mensuel_centimes"] == 119_000_00

    # Vérification en base de données
    with schema_context(get_public_schema_name()):
        abo = entreprise_test.abonnements.first()
        abo.refresh_from_db()
        assert abo.plan.code == "PROMOTEUR"

        entree_audit = JournalPlateforme.objects.filter(
            entreprise_id=entreprise_test.id, action="CHANGEMENT_PLAN"
        ).first()
        assert entree_audit is not None
        assert entree_audit.detail["nouveau_plan"] == "PROMOTEUR"


@pytest.mark.django_db
def test_changer_plan_client_alias_mock_succes(client_api, super_admin_user, entreprise_test):
    """Vérifie que l'alias 'PRO' du frontend mock est correctement résolu vers 'MAITRE_OEUVRE'."""
    client_api.force_authenticate(user=super_admin_user)

    url = f"/api/v1/admins/clients/{entreprise_test.id}/abonnement/"
    payload = {"plan_code": "PRO"}

    reponse = client_api.patch(url, data=payload, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    client = reponse.json()
    assert client["abonnement"]["plan_code"] == "MAITRE_OEUVRE"
    assert client["abonnement"]["montant_mensuel_centimes"] == 49_000_00


@pytest.mark.django_db
def test_changer_plan_inconnu_400(client_api, super_admin_user, entreprise_test):
    """Vérifie qu'un plan inexistant renvoie une erreur de validation 400."""
    client_api.force_authenticate(user=super_admin_user)

    url = f"/api/v1/admins/clients/{entreprise_test.id}/abonnement/"
    payload = {"plan_code": "PLAN_INEXISTANT"}

    reponse = client_api.patch(url, data=payload, format="json")

    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
