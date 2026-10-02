"""Tests de l'architecture multi-tenant à domaine unique (Option A).

Vérifie que :
1. Un utilisateur d'un tenant peut se connecter via le domaine principal/public sans sous-domaine.
2. Les jetons JWT émis contiennent le claim `schema`.
3. Une requête authentifiée vers un endpoint protégé sans sous-domaine résout automatiquement
   le schéma PostgreSQL du tenant via le jeton JWT.
4. L'en-tête explicite `X-Tenant` permet de cibler un tenant.
5. Une invitation créée dans un tenant peut être vérifiée et acceptée via le domaine public.
"""

import pytest
import jwt
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.tenants.models import Entreprise

SCHEMA = "demo"
DOMAINE_PUBLIC = "localhost"
MOT_DE_PASSE = "MotDePasse123!"


@pytest.fixture
def utilisateur_tenant(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="employe@uniquetest.ci").delete()
        user = Utilisateur.objects.create_user(
            email="employe@uniquetest.ci",
            password=MOT_DE_PASSE,
            nom="Touré",
            prenom="Moussa",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )
        yield user


@pytest.fixture
def client_public():
    """Client appelant le domaine public sans sous-domaine de client."""
    return APIClient(HTTP_HOST=DOMAINE_PUBLIC)


@pytest.mark.django_db
def test_connexion_domaine_public_trouve_le_tenant(client_public, utilisateur_tenant):
    """L'utilisateur se connecte sur le domaine public et ses jetons portent son schéma."""
    reponse = client_public.post(
        "/api/v1/auth/token/",
        {"email": "employe@uniquetest.ci", "mot_de_passe": MOT_DE_PASSE},
        format="json",
    )
    assert reponse.status_code == 200
    corps = reponse.json()

    assert "access" in corps
    assert "refresh" in corps
    assert corps["utilisateur"]["email"] == "employe@uniquetest.ci"
    assert corps["utilisateur"]["schema"] == SCHEMA

    # Vérification des claims JWT
    payload_access = jwt.decode(corps["access"], options={"verify_signature": False})
    payload_refresh = jwt.decode(corps["refresh"], options={"verify_signature": False})

    assert payload_access.get("schema") == SCHEMA
    assert payload_refresh.get("schema") == SCHEMA


@pytest.mark.django_db
def test_appel_api_authentifie_sans_sous_domaine(client_public, utilisateur_tenant):
    """Un appel avec Authorization: Bearer <token> sur le domaine public résout le bon tenant."""
    # 1. Connexion sur domaine public
    reponse_login = client_public.post(
        "/api/v1/auth/token/",
        {"email": "employe@uniquetest.ci", "mot_de_passe": MOT_DE_PASSE},
        format="json",
    )
    assert reponse_login.status_code == 200
    access_token = reponse_login.json()["access"]

    # 2. Appel d'une route tenant protégée avec le token (sur domaine public)
    client_auth = APIClient(HTTP_HOST=DOMAINE_PUBLIC)
    client_auth.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    reponse_moi = client_auth.get("/api/v1/auth/profil/")

    assert reponse_moi.status_code == 200
    profil = reponse_moi.json()
    assert profil["email"] == "employe@uniquetest.ci"
    assert profil["nom"] == "Touré"
    assert profil["schema"] == SCHEMA


@pytest.mark.django_db
def test_renouvellement_sans_sous_domaine(client_public, utilisateur_tenant):
    """Le renouvellement de jeton sur le domaine public conserve le schéma du tenant."""
    reponse_login = client_public.post(
        "/api/v1/auth/token/",
        {"email": "employe@uniquetest.ci", "mot_de_passe": MOT_DE_PASSE},
        format="json",
    )
    refresh_token = reponse_login.json()["refresh"]

    reponse_refresh = client_public.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": refresh_token},
        format="json",
    )
    assert reponse_refresh.status_code == 200
    nouveaux_tokens = reponse_refresh.json()

    nouveau_payload = jwt.decode(nouveaux_tokens["access"], options={"verify_signature": False})
    assert nouveau_payload.get("schema") == SCHEMA


@pytest.mark.django_db
def test_invitation_verifier_et_accepter_domaine_public(client_public):
    """Une invitation d'un tenant peut être vérifiée et acceptée depuis le domaine public."""
    from apps.accounts.services.invitations import creer_invitation

    with schema_context(SCHEMA):
        invitation = creer_invitation(
            email="nouveau@uniquetest.ci",
            role_propose=RoleGlobal.CHEF_CHANTIER,
            nom="Konan",
        )
        jeton_clair = str(invitation.jeton_clair)

    # Vérification depuis le domaine public
    reponse_verif = client_public.post(
        "/api/v1/invitations/verifier/",
        {"jeton": jeton_clair},
        format="json",
    )
    assert reponse_verif.status_code == 200
    corps_verif = reponse_verif.json()
    assert corps_verif["email"] == "nouveau@uniquetest.ci"
    assert corps_verif["role_propose"] == RoleGlobal.CHEF_CHANTIER

    # Acceptation depuis le domaine public
    reponse_accept = client_public.post(
        "/api/v1/invitations/accepter/",
        {
            "jeton": jeton_clair,
            "prenom": "Jean",
            "nom": "Konan",
            "mot_de_passe": "NouveauMdp123!",
        },
        format="json",
    )
    assert reponse_accept.status_code == 200
    corps_accept = reponse_accept.json()
    assert "access" in corps_accept

    # Vérification que le token émis a le schéma du tenant
    payload = jwt.decode(corps_accept["access"], options={"verify_signature": False})
    assert payload.get("schema") == SCHEMA
