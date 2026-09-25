"""Tests pour les APIs du profil utilisateur (/api/v1/auth/profil/).

Couvre :
- Consultation du profil complet (GET)
- Protection contre l'accès anonyme (401)
- Mise à jour partielle sécurisée (PATCH)
- Protection contre le mass-assignment (élévation de privilèges, modification d'email)
- Changement de mot de passe connecté avec réémission de tokens et révocation
- Téléversement, format et suppression d'avatar
"""

import io

import pytest
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import schema_context
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"
ANCIEN_MDP = "Secret12345!"
NOUVEAU_MDP = "NouveauSecret6789@"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def utilisateur(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="test.profil@demo.ci",
            defaults={
                "nom": "Kouadio",
                "prenom": "Jean",
                "telephone": "+2250701020304",
                "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
                "doit_changer_mot_de_passe": True,
            },
        )
        user.nom = "Kouadio"
        user.prenom = "Jean"
        user.telephone = "+2250701020304"
        user.role_global = RoleGlobal.CONDUCTEUR_TRAVAUX
        user.is_owner = False
        user.password = make_password(ANCIEN_MDP)
        user.doit_changer_mot_de_passe = True
        user.save()
        return user


@pytest.mark.django_db
def test_profil_consultation_authentifie(client, utilisateur):
    """GET /api/v1/auth/profil/ retourne le profil complet enrichi."""
    client.force_authenticate(user=utilisateur)
    response = client.get("/api/v1/auth/profil/")

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["id"] == str(utilisateur.pk)
    assert data["email"] == "test.profil@demo.ci"
    assert data["nom"] == "Kouadio"
    assert data["prenom"] == "Jean"
    assert data["nom_complet"] == "Jean Kouadio"
    assert data["telephone"] == "+2250701020304"
    assert data["initiales"] == "JK"
    assert data["role_global"] == RoleGlobal.CONDUCTEUR_TRAVAUX
    assert data["is_dg"] is False
    assert data["is_owner"] is False
    assert data["doit_changer_mot_de_passe"] is True
    assert "habilitations" in data
    assert "schema" in data


@pytest.mark.django_db
def test_profil_consultation_anonyme_refusee(client):
    """GET /api/v1/auth/profil/ sans authentification renvoie 401."""
    response = client.get("/api/v1/auth/profil/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_profil_mise_a_jour_partielle_succes(client, utilisateur):
    """PATCH /api/v1/auth/profil/ met à jour les coordonnées autorisées."""
    client.force_authenticate(user=utilisateur)
    payload = {
        "prenom": "Jean-Marc",
        "telephone": "+2250799887766",
        "langue": "en",
    }
    response = client.patch("/api/v1/auth/profil/", data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["prenom"] == "Jean-Marc"
    assert response.data["telephone"] == "+2250799887766"
    assert response.data["langue"] == "en"

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert utilisateur.prenom == "Jean-Marc"
        assert utilisateur.telephone == "+2250799887766"
        assert utilisateur.langue == "en"


@pytest.mark.django_db
def test_profil_protection_mass_assignment(client, utilisateur):
    """PATCH /api/v1/auth/profil/ ignore ou interdit l'élévation de privilèges."""
    client.force_authenticate(user=utilisateur)
    payload = {
        "role_global": RoleGlobal.DIRECTEUR_GENERAL,
        "is_owner": True,
        "email": "hacker@demo.ci",
        "statut": StatutUtilisateur.DESACTIVE,
        "prenom": "Valide",
    }
    response = client.patch("/api/v1/auth/profil/", data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["prenom"] == "Valide"

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert utilisateur.prenom == "Valide"
        assert utilisateur.role_global == RoleGlobal.CONDUCTEUR_TRAVAUX
        assert utilisateur.is_owner is False
        assert utilisateur.email == "test.profil@demo.ci"
        assert utilisateur.statut == StatutUtilisateur.ACTIF


@pytest.mark.django_db
def test_profil_mise_a_jour_telephone_invalide(client, utilisateur):
    """PATCH /api/v1/auth/profil/ refuse un numéro de téléphone invalide."""
    client.force_authenticate(user=utilisateur)
    response = client.patch("/api/v1/auth/profil/", data={"telephone": "invalide"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_changement_mot_de_passe_succes(client, utilisateur):
    """POST /api/v1/auth/profil/mot-de-passe/ change le mot de passe et réémet les jetons."""
    client.force_authenticate(user=utilisateur)
    payload = {
        "ancien_mot_de_passe": ANCIEN_MDP,
        "nouveau_mot_de_passe": NOUVEAU_MDP,
        "origine": "WEB",
    }
    response = client.post("/api/v1/auth/profil/mot-de-passe/", data=payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data
    assert "expire_dans" in response.data

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert utilisateur.check_password(NOUVEAU_MDP) is True
        assert utilisateur.check_password(ANCIEN_MDP) is False
        assert utilisateur.doit_changer_mot_de_passe is False


@pytest.mark.django_db
def test_changement_mot_de_passe_ancien_invalide(client, utilisateur):
    """POST /api/v1/auth/profil/mot-de-passe/ échoue si l'ancien mot de passe est faux."""
    client.force_authenticate(user=utilisateur)
    payload = {
        "ancien_mot_de_passe": "FauxMotDePasse123!",
        "nouveau_mot_de_passe": NOUVEAU_MDP,
    }
    response = client.post("/api/v1/auth/profil/mot-de-passe/", data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["erreur"]["code"] == "ancien_mot_de_passe_incorrect"

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert utilisateur.check_password(ANCIEN_MDP) is True


@pytest.mark.django_db
def test_changement_mot_de_passe_identique_refuse(client, utilisateur):
    """POST /api/v1/auth/profil/mot-de-passe/ refuse un nouveau MDP identique à l'ancien."""
    client.force_authenticate(user=utilisateur)
    payload = {
        "ancien_mot_de_passe": ANCIEN_MDP,
        "nouveau_mot_de_passe": ANCIEN_MDP,
    }
    response = client.post("/api/v1/auth/profil/mot-de-passe/", data=payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["erreur"]["code"] == "mot_de_passe_identique"


@pytest.mark.django_db
def test_upload_avatar_succes_et_suppression(client, utilisateur):
    """POST et DELETE /api/v1/auth/profil/avatar/ pour gérer la photo de profil."""
    client.force_authenticate(user=utilisateur)

    # Création d'une image test valide en mémoire
    img = Image.new("RGB", (400, 300), color="blue")
    tampon = io.BytesIO()
    img.save(tampon, format="PNG")
    tampon.seek(0)
    fichier = SimpleUploadedFile("avatar_test.png", tampon.getvalue(), content_type="image/png")

    # 1. Upload
    response_post = client.post(
        "/api/v1/auth/profil/avatar/",
        data={"avatar": fichier},
        format="multipart",
    )
    assert response_post.status_code == status.HTTP_200_OK
    avatar_url = response_post.data["avatar_url"]
    assert avatar_url is not None
    assert "webp" in avatar_url

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert bool(utilisateur.avatar) is True

    # 2. Suppression
    response_del = client.delete("/api/v1/auth/profil/avatar/")
    assert response_del.status_code == status.HTTP_200_OK
    assert response_del.data["avatar_url"] is None

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert bool(utilisateur.avatar) is False


@pytest.mark.django_db
def test_upload_avatar_fichier_invalide(client, utilisateur):
    """POST /api/v1/auth/profil/avatar/ refuse un fichier non-image."""
    client.force_authenticate(user=utilisateur)
    fichier_texte = SimpleUploadedFile(
        "malware.txt", b"Faux contenu texte", content_type="text/plain"
    )

    response = client.post(
        "/api/v1/auth/profil/avatar/",
        data={"avatar": fichier_texte},
        format="multipart",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
