import io
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import schema_context
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal
from apps.tenants.models import Entreprise

HOTE = "demo.localhost"
SCHEMA = "demo"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def admin_demo(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="admin.config@ccd-digital.ci",
            defaults={"is_active": True, "role_global": RoleGlobal.ADMIN},
        )
        user.role_global = RoleGlobal.ADMIN
        user.set_password("MotDePasse1!")
        user.save()
        return user


@pytest.fixture
def dg_demo(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="dg.config@ccd-digital.ci",
            defaults={"is_active": True, "role_global": RoleGlobal.DIRECTEUR_GENERAL},
        )
        user.role_global = RoleGlobal.DIRECTEUR_GENERAL
        user.set_password("MotDePasse1!")
        user.save()
        return user


@pytest.fixture
def visiteur_demo(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="visiteur.config@ccd-digital.ci",
            defaults={"is_active": True, "role_global": RoleGlobal.VISITEUR},
        )
        user.role_global = RoleGlobal.VISITEUR
        user.set_password("MotDePasse1!")
        user.save()
        return user


def _creer_image_test():
    fichier = io.BytesIO()
    image = Image.new("RGB", (40, 40), color=(10, 80, 160))
    image.save(fichier, format="PNG")
    fichier.seek(0)
    return SimpleUploadedFile("logo_config_test.png", fichier.read(), content_type="image/png")


@pytest.mark.django_db
def test_lecture_configuration_entreprise(client, visiteur_demo):
    """Tout utilisateur authentifié du tenant peut lire la configuration."""
    client.force_authenticate(user=visiteur_demo)
    reponse = client.get("/api/v1/parametres/configuration/")
    assert reponse.status_code == status.HTTP_200_OK
    assert "raison_sociale" in reponse.data
    assert "pays" in reponse.data


@pytest.mark.django_db
def test_post_configuration_entreprise_par_admin(client, admin_demo):
    """Un administrateur peut enregistrer la configuration en POST."""
    client.force_authenticate(user=admin_demo)
    reponse = client.post(
        "/api/v1/parametres/configuration/",
        {
            "raison_sociale": "Nouvelle Raison Sociale SARL",
            "nom_commercial": "NRS BTP",
            "adresse": "Zone Industrielle Yopougon",
            "ville": "Abidjan",
            "rccm": "CI-ABJ-2026-B-9999",
            "nif": "99999999Z",
            "telephone_contact": "+2250701020304",
            "email_contact": "contact@nrs-btp.ci",
        },
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["raison_sociale"] == "Nouvelle Raison Sociale SARL"
    assert reponse.data["nom_commercial"] == "NRS BTP"
    assert reponse.data["ville"] == "Abidjan"
    assert reponse.data["rccm"] == "CI-ABJ-2026-B-9999"

    with schema_context("public"):
        entreprise = Entreprise.objects.get(schema_name=SCHEMA)
        assert entreprise.raison_sociale == "Nouvelle Raison Sociale SARL"
        assert entreprise.nom_commercial == "NRS BTP"
        assert entreprise.ville == "Abidjan"


@pytest.mark.django_db
def test_post_configuration_entreprise_par_dg(client, dg_demo):
    """Un Directeur Général peut également enregistrer la configuration en POST."""
    client.force_authenticate(user=dg_demo)
    reponse = client.post(
        "/api/v1/parametres/configuration/",
        {"nom_commercial": "DG Entreprise Test"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["nom_commercial"] == "DG Entreprise Test"


@pytest.mark.django_db
def test_post_configuration_entreprise_refuse_aux_non_admins(client, visiteur_demo):
    """Les rôles non-admin (ex: Visiteur, Chef de chantier) reçoivent 403 Forbidden sur POST."""
    client.force_authenticate(user=visiteur_demo)
    reponse = client.post(
        "/api/v1/parametres/configuration/",
        {"nom_commercial": "Piratage"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_post_configuration_entreprise_avec_logo(client, admin_demo, settings, tmp_path):
    """POST avec fichier_logo multipart génère les 3 variantes de logos."""
    settings.MEDIA_ROOT = tmp_path
    client.force_authenticate(user=admin_demo)
    image = _creer_image_test()

    reponse = client.post(
        "/api/v1/parametres/configuration/",
        {
            "nom_commercial": "Entreprise Logo",
            "fichier_logo": image,
        },
        format="multipart",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["nom_commercial"] == "Entreprise Logo"
    assert reponse.data["logo"].endswith("_2x.png")
    assert reponse.data["logo_1x"].endswith("_1x.png")
    assert reponse.data["logo_original"].endswith("_original.png")
    assert "fond_retire" in reponse.data


@pytest.mark.django_db
def test_post_configuration_entreprise_retirer_logo(client, admin_demo, settings, tmp_path):
    """POST avec retirer_logo=True efface le logo."""
    settings.MEDIA_ROOT = tmp_path
    client.force_authenticate(user=admin_demo)

    # D'abord on met un logo
    client.post(
        "/api/v1/parametres/configuration/",
        {"fichier_logo": _creer_image_test()},
        format="multipart",
    )
    # Ensuite on le retire
    reponse = client.post(
        "/api/v1/parametres/configuration/",
        {"retirer_logo": True},
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["logo"] == ""
    assert reponse.data["logo_1x"] == ""
    assert reponse.data["logo_original"] == ""


@pytest.mark.django_db
def test_patch_configuration_entreprise(client, admin_demo):
    """La méthode PATCH reste également fonctionnelle sur /parametres/configuration/."""
    client.force_authenticate(user=admin_demo)
    reponse = client.patch(
        "/api/v1/parametres/configuration/",
        {"nom_commercial": "Patch Test"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["nom_commercial"] == "Patch Test"


@pytest.mark.django_db
def test_post_entreprise_retrocompatibilite(client, admin_demo):
    """L'ancienne route /api/v1/entreprise/ accepte maintenant aussi le POST."""
    client.force_authenticate(user=admin_demo)
    reponse = client.post(
        "/api/v1/entreprise/",
        {"nom_commercial": "Retro POST Test"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["nom_commercial"] == "Retro POST Test"
