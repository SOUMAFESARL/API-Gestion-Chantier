"""Tests complets pour l'assistance Super Admin (Impersonification) et JournalPlateforme.

Valide :
- R-128 : L'impersonification est en lecture seule absolue et tracée des deux côtés.
- Test 10 : Une impersonification écrit dans les deux journaux (JournalPlateforme & JournalAudit).
- Test 11 : Une écriture tentée pendant une impersonification est systématiquement refusée (HTTP 403).
- Session limitée à 1 heure (3600 secondes), non renouvelable.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import Entreprise

SCHEMA_CLIENT = "demo"
HOTE_PLATEFORME = "localhost"
HOTE_CLIENT = "demo.localhost"


@pytest.fixture(autouse=True)
def autoriser_ip_locale(settings):
    """Autorise l'adresse IP de test dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]


@pytest.fixture
def super_admin_user(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superadmin.test@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="superadmin.test@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Super",
            prenom="Admin",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_staff=True,
        )


@pytest.fixture
def client_dg_user(db):
    """Crée un utilisateur DG dans le schéma tenant demo."""
    with schema_context(SCHEMA_CLIENT):
        Utilisateur.tous_objets.filter(email="dg.client@demo.ci").delete()
        return Utilisateur.objects.create_user(
            email="dg.client@demo.ci",
            password="ClientPassword123!",
            nom="Directeur",
            prenom="General",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )


@pytest.fixture
def entreprise_demo(db):
    """Récupère l'entreprise demo configurée dans conftest."""
    with schema_context(get_public_schema_name()):
        return Entreprise.objects.get(schema_name=SCHEMA_CLIENT)


@pytest.fixture
def client_api():
    """Client API positionné sur la plateforme."""
    return APIClient(headers={"host": HOTE_PLATEFORME})


@pytest.mark.django_db
def test_demarrer_assistance_succes_et_double_trace(
    client_api, super_admin_user, client_dg_user, entreprise_demo
):
    """Test 10 & R-128 : Démarrage d'assistance avec succès et écriture dans les deux journaux."""
    client_api.force_authenticate(user=super_admin_user)

    url = f"/api/v1/admins/entreprises/{entreprise_demo.id}/assistance/"
    motif = "Demande d'assistance pour débloquer le devis #42"

    reponse = client_api.post(
        url,
        {"motif": motif, "utilisateur_id": str(client_dg_user.id)},
        format="json",
    )

    assert reponse.status_code == status.HTTP_200_OK
    data = reponse.data
    assert "access" in data
    assert data["expire_dans"] == 3600
    assert data["impersonation"]["actif"] is True
    assert data["impersonation"]["mode"] == "LECTURE_SEULE"
    assert data["impersonation"]["super_admin"]["email"] == super_admin_user.email
    assert data["impersonation"]["utilisateur"]["email"] == client_dg_user.email

    # 1. Vérification du JournalPlateforme (schéma public)
    with schema_context(get_public_schema_name()):
        log_plateforme = (
            JournalPlateforme.objects.filter(
                action="CONNEXION_ASSISTANCE",
                utilisateur_id=super_admin_user.id,
                entreprise_id=entreprise_demo.id,
            )
            .order_by("-horodatage")
            .first()
        )
        assert log_plateforme is not None
        assert log_plateforme.detail["motif"] == motif
        assert log_plateforme.detail["cible_email"] == client_dg_user.email
        assert log_plateforme.detail["mode"] == "LECTURE_SEULE"

    # 2. Vérification du JournalAudit (schéma tenant client)
    with schema_context(SCHEMA_CLIENT):
        log_client = (
            JournalAudit.objects.filter(
                action=ActionAudit.ASSISTANCE,
                utilisateur_id=client_dg_user.id,
            )
            .order_by("-horodatage")
            .first()
        )
        assert log_client is not None
        assert log_client.valeur_apres["super_admin_email"] == super_admin_user.email
        assert log_client.valeur_apres["motif"] == motif
        assert log_client.valeur_apres["mode"] == "LECTURE_SEULE"


@pytest.mark.django_db
def test_demande_assistance_motif_obligatoire_min_5_caracteres(
    client_api, super_admin_user, entreprise_demo
):
    """Arbitrage 2 : Le motif d'intervention est obligatoire et requiert au moins 5 caractères."""
    client_api.force_authenticate(user=super_admin_user)
    url = f"/api/v1/admins/entreprises/{entreprise_demo.id}/assistance/"

    # Sans motif
    rep_vide = client_api.post(url, {"motif": ""}, format="json")
    assert rep_vide.status_code == status.HTTP_400_BAD_REQUEST

    # Motif trop court (< 5 caractères)
    rep_court = client_api.post(url, {"motif": "Aide"}, format="json")
    assert rep_court.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_demande_assistance_refusee_si_non_super_admin(
    client_api, client_dg_user, entreprise_demo
):
    """Seul un Super Admin du schéma public peut démarrer une session d'assistance."""
    client_api.force_authenticate(user=client_dg_user)
    url = f"/api/v1/admins/entreprises/{entreprise_demo.id}/assistance/"

    rep = client_api.post(url, {"motif": "Tentative non autorisée"}, format="json")
    assert rep.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)


@pytest.mark.django_db
def test_mode_assistance_bloque_toute_ecriture_et_autorise_lecture(
    client_api, super_admin_user, client_dg_user, entreprise_demo
):
    """Test 11 & R-128 : Toute écriture tentée pendant une impersonification est refusée (HTTP 403)."""
    # 1. Obtenir un jeton d'assistance
    client_api.force_authenticate(user=super_admin_user)
    url_assistance = f"/api/v1/admins/entreprises/{entreprise_demo.id}/assistance/"
    rep_init = client_api.post(
        url_assistance,
        {"motif": "Test de restriction lecture seule"},
        format="json",
    )
    assert rep_init.status_code == status.HTTP_200_OK
    token_assistance = rep_init.data["access"]

    # 2. Client HTTP utilisant le jeton d'assistance sur le tenant client
    client_assistance = APIClient(headers={"host": HOTE_CLIENT})
    client_assistance.credentials(HTTP_AUTHORIZATION=f"Bearer {token_assistance}")

    # A. La lecture (GET) doit être autorisée
    rep_lecture = client_assistance.get("/api/v1/utilisateurs/moi/")
    assert rep_lecture.status_code == status.HTTP_200_OK
    assert rep_lecture.data["email"] == client_dg_user.email

    # B. L'écriture (POST) doit être strictement bloquée avec 403
    rep_ecriture = client_assistance.post(
        "/api/v1/roles/",
        {"code": "TEST", "nom": "Nouveau Rôle"},
        format="json",
    )
    assert rep_ecriture.status_code == status.HTTP_403_FORBIDDEN
    data_rep = rep_ecriture.json() if hasattr(rep_ecriture, "json") else rep_ecriture.data
    assert data_rep["erreur"]["code"] == "ecriture_interdite_assistance"

    # C. Vérifier que la tentative d'écriture a été consignée dans JournalPlateforme
    with schema_context(get_public_schema_name()):
        log_tentative = (
            JournalPlateforme.objects.filter(
                action="TENTATIVE_ECRITURE_BLOQUEE",
                utilisateur_id=super_admin_user.id,
            )
            .order_by("-horodatage")
            .first()
        )
        assert log_tentative is not None
        assert log_tentative.detail["methode"] == "POST"


@pytest.mark.django_db
def test_clore_session_assistance_et_journal_plateforme(
    client_api, super_admin_user, entreprise_demo
):
    """Déconnexion de session d'assistance et consultation du journal plateforme."""
    client_api.force_authenticate(user=super_admin_user)

    # Déconnexion
    rep_deconnexion = client_api.post(
        "/api/v1/admins/assistance/deconnexion/",
        {"entreprise_id": str(entreprise_demo.id)},
        format="json",
    )
    assert rep_deconnexion.status_code == status.HTTP_200_OK
    assert rep_deconnexion.data["statut"] == "deconnecte"

    # Consultation du journal plateforme
    rep_journal = client_api.get("/api/v1/admins/journal-plateforme/")
    assert rep_journal.status_code == status.HTTP_200_OK
    assert isinstance(rep_journal.data, list)
    actions = [entree["action"] for entree in rep_journal.data]
    assert "DECONNEXION_ASSISTANCE" in actions


@pytest.mark.django_db
def test_lister_utilisateurs_entreprise(
    client_api, super_admin_user, client_dg_user, entreprise_demo
):
    """Vérifie que le Super Admin peut lister les utilisateurs d'une entreprise pour cibler l'assistance."""
    client_api.force_authenticate(user=super_admin_user)
    url = f"/api/v1/admins/entreprises/{entreprise_demo.id}/utilisateurs/"

    rep = client_api.get(url)
    assert rep.status_code == status.HTTP_200_OK
    assert isinstance(rep.data, list)
    emails = [u["email"] for u in rep.data]
    assert client_dg_user.email in emails
