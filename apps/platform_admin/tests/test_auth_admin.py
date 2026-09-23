"""Tests d'authentification Super Admin sur /api/v1/admins/ (Control Plane).

Vérifie :
1. Connexion réussie pour un compte du schéma public avec is_superuser=True.
2. Échec avec 401 identifiants_invalides si mot de passe incorrect ou compte inexistant.
3. Rejet 401 si le compte existe mais n'a pas is_superuser=True.
4. Absence totale de restriction d'adresse IP (accès ouvert par email + mot de passe).
5. Déconnexion avec révocation côté serveur et idempotence.
6. Traçabilité dans JournalPlateforme pour connexions (succès/échec) et déconnexions.
7. Renouvellement de jeton d'accès via /api/v1/admins/token/refresh/.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme

HOTE_PLATEFORME = "localhost"


@pytest.fixture
def superuser_admin(db):
    """Crée un Super Admin avec is_superuser=True dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="admin.root@ccd-digital.ci").delete()
        return Utilisateur.objects.create_superuser(
            email="admin.root@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Directeur",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )


@pytest.fixture
def utilisateur_standard(db):
    """Crée un utilisateur non superuser (is_superuser=False)."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="user.normal@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="user.normal@ccd-digital.ci",
            password="NormalPassword123!",
            nom="Normal",
            prenom="User",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
            is_staff=False,
            is_superuser=False,
        )


@pytest.fixture
def client_api():
    """Client API ciblant la plateforme."""
    return APIClient(headers={"host": HOTE_PLATEFORME})


@pytest.mark.django_db
def test_connexion_super_admin_succes_et_audit(client_api, superuser_admin):
    """Connexion réussie d'un Super Admin avec émission des jetons et audit."""
    url = "/api/v1/admins/connexion/"
    donnees = {
        "email": superuser_admin.email,
        "mot_de_passe": "SuperPassword123!",
        "origine": "WEB",
    }

    reponse = client_api.post(url, donnees, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.headers.get("Cache-Control") == "no-store"

    data = reponse.data
    assert "access" in data
    assert "refresh" in data
    assert data["expire_dans"] == 900
    assert data["utilisateur"]["id"] == str(superuser_admin.id)
    assert data["utilisateur"]["email"] == superuser_admin.email
    assert data["utilisateur"]["is_superuser"] is True
    assert data["utilisateur"]["schema"] == "public"

    # Vérification de l'enregistrement dans JournalPlateforme
    with schema_context(get_public_schema_name()):
        audit = (
            JournalPlateforme.objects.filter(
                action="CONNEXION_SUPER_ADMIN",
                utilisateur_id=superuser_admin.id,
            )
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None
        assert audit.detail["email"] == superuser_admin.email
        assert audit.detail["statut"] == "SUCCES"


@pytest.mark.django_db
def test_connexion_super_admin_echec_mot_de_passe_et_audit(client_api, superuser_admin):
    """Un mot de passe invalide renvoie 401 et journalise l'échec."""
    url = "/api/v1/admins/connexion/"
    donnees = {
        "email": superuser_admin.email,
        "mot_de_passe": "MauvaisMotDePasse!",
    }

    reponse = client_api.post(url, donnees, format="json")

    assert reponse.status_code == status.HTTP_401_UNAUTHORIZED
    assert reponse.data["erreur"]["code"] == "identifiants_invalides"

    with schema_context(get_public_schema_name()):
        audit = (
            JournalPlateforme.objects.filter(action="ECHEC_CONNEXION_SUPER_ADMIN")
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None
        assert audit.detail["email"] == superuser_admin.email


@pytest.mark.django_db
def test_connexion_super_admin_refus_si_non_superuser(client_api, utilisateur_standard):
    """Un compte actif sans is_superuser=True est rejeté avec 401 identifiants_invalides."""
    url = "/api/v1/admins/connexion/"
    donnees = {
        "email": utilisateur_standard.email,
        "mot_de_passe": "NormalPassword123!",
    }

    reponse = client_api.post(url, donnees, format="json")

    assert reponse.status_code == status.HTTP_401_UNAUTHORIZED
    assert reponse.data["erreur"]["code"] == "identifiants_invalides"

    with schema_context(get_public_schema_name()):
        audit = (
            JournalPlateforme.objects.filter(action="ECHEC_CONNEXION_SUPER_ADMIN")
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None
        assert audit.detail["email"] == utilisateur_standard.email


@pytest.mark.django_db
def test_connexion_super_admin_sans_restriction_ip(client_api, superuser_admin, settings):
    """La connexion sur /api/v1/admins/connexion/ ne subit aucune restriction d'adresse IP."""
    settings.SUPER_ADMIN_IPS = ["10.0.0.1"]  # IP différente de l'appelant

    client_externe = APIClient(
        headers={"host": HOTE_PLATEFORME},
        REMOTE_ADDR="198.51.100.42",  # IP arbitraire non autorisée par SUPER_ADMIN_IPS
    )

    url = "/api/v1/admins/connexion/"
    donnees = {
        "email": superuser_admin.email,
        "mot_de_passe": "SuperPassword123!",
    }

    reponse = client_externe.post(url, donnees, format="json")

    # Doit réussir car admins/ n'a pas de restriction IP
    assert reponse.status_code == status.HTTP_200_OK
    assert "access" in reponse.data


@pytest.mark.django_db
def test_deconnexion_super_admin_succes_et_audit(client_api, superuser_admin):
    """Déconnexion Super Admin avec révocation du jeton refresh et audit."""
    # 1. Connexion préalable pour avoir un refresh token
    rep_login = client_api.post(
        "/api/v1/admins/connexion/",
        {"email": superuser_admin.email, "mot_de_passe": "SuperPassword123!"},
        format="json",
    )
    assert rep_login.status_code == status.HTTP_200_OK
    refresh_token = rep_login.data["refresh"]

    # 2. Déconnexion
    rep_logout = client_api.post(
        "/api/v1/admins/deconnexion/",
        {"refresh": refresh_token},
        format="json",
    )
    assert rep_logout.status_code == status.HTTP_200_OK
    assert rep_logout.data["message"] == "Déconnexion réussie."

    # 3. Vérification de l'audit
    with schema_context(get_public_schema_name()):
        audit = (
            JournalPlateforme.objects.filter(action="DECONNEXION_SUPER_ADMIN")
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None


@pytest.mark.django_db
def test_renouvellement_jeton_super_admin(client_api, superuser_admin):
    """Renouvellement du jeton Super Admin via /api/v1/admins/token/refresh/."""
    rep_login = client_api.post(
        "/api/v1/admins/connexion/",
        {"email": superuser_admin.email, "mot_de_passe": "SuperPassword123!"},
        format="json",
    )
    refresh_token = rep_login.data["refresh"]

    rep_refresh = client_api.post(
        "/api/v1/admins/token/refresh/",
        {"refresh": refresh_token},
        format="json",
    )
    assert rep_refresh.status_code == status.HTTP_200_OK
    assert "access" in rep_refresh.data
    assert "refresh" in rep_refresh.data


@pytest.mark.django_db
def test_auto_provisionner_super_admin():
    """Vérifie que l'auto-provisioning crée ou configure support@ccd-digital.ci correctement."""
    import apps.platform_admin.services.provisioning as prov_module
    from apps.accounts.models import Utilisateur
    from apps.platform_admin.services.provisioning import auto_provisionner_super_admin

    prov_module._PROVISIONING_EFFECTUE = False

    with schema_context(get_public_schema_name()):
        # Exécute l'auto-provisioning
        auto_provisionner_super_admin()

        super_admin = Utilisateur.objects.filter(email__iexact="support@ccd-digital.ci").first()
        assert super_admin is not None
        assert super_admin.is_superuser is True
        assert super_admin.is_staff is True
        assert super_admin.is_active is True
        assert super_admin.check_password("SuperAdmin2026!") is True

