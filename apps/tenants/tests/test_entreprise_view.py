import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import schema_context
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.tenants.models import Entreprise

HOTE = "demo.localhost"
SCHEMA = "demo"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def utilisateur_demo(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="test.entreprise@ccd-digital.ci",
            defaults={"is_active": True},
        )
        user.set_password("MotDePasse1!")
        user.save()
        return user


def _creer_image_test():
    fichier = io.BytesIO()
    image = Image.new("RGB", (30, 30), color=(30, 96, 145))
    image.save(fichier, format="PNG")
    fichier.seek(0)
    return SimpleUploadedFile("logo_test.png", fichier.read(), content_type="image/png")


@pytest.mark.django_db
def test_lecture_entreprise(client, utilisateur_demo):
    client.force_authenticate(user=utilisateur_demo)
    reponse = client.get("/api/v1/entreprise/")
    assert reponse.status_code == status.HTTP_200_OK
    assert "raison_sociale" in reponse.data
    assert "couleur_primaire" in reponse.data


@pytest.mark.django_db
def test_modification_entreprise_avec_logo_et_couleur(client, utilisateur_demo, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_authenticate(user=utilisateur_demo)
    image = _creer_image_test()

    reponse = client.patch(
        "/api/v1/entreprise/",
        {
            "nom_commercial": "SOUMAFE BTP",
            "couleur_primaire": "#1E6091",
            "fichier_logo": image,
        },
        format="multipart",
    )

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["nom_commercial"] == "SOUMAFE BTP"
    assert reponse.data["couleur_primaire"] == "#1E6091"

    # Les trois variantes remontent, en URL absolues, prêtes pour un `srcset`.
    assert reponse.data["logo"].endswith("_2x.png")
    assert reponse.data["logo_1x"].endswith("_1x.png")
    assert reponse.data["logo_original"].endswith("_original.png")
    for url in (reponse.data["logo"], reponse.data["logo_1x"], reponse.data["logo_original"]):
        assert url.startswith("http://")
        assert "/media/" + SCHEMA + "/logos/" in url

    # Le verdict de détourage accompagne l'envoi — il n'est jamais stocké.
    assert reponse.data["fond_retire"] is False

    with schema_context("public"):
        entreprise = Entreprise.objects.get(schema_name=SCHEMA)
        assert entreprise.couleur_primaire == "#1E6091"
        # En base, des clés de stockage — jamais des URL : une URL S3 est
        # signée, et une URL signée persistée est un lien qui meurt.
        assert entreprise.logo.startswith(f"{SCHEMA}/logos/")
        assert not entreprise.logo.startswith("/media/")
        assert entreprise.logo_1x.endswith("_1x.png")
        assert entreprise.logo_original.endswith("_original.png")


@pytest.mark.django_db
def test_retrait_du_logo(client, utilisateur_demo, settings, tmp_path):
    """`retirer_logo` efface les trois variantes — `logo: ""` ne le peut plus."""
    settings.MEDIA_ROOT = tmp_path
    client.force_authenticate(user=utilisateur_demo)

    client.patch("/api/v1/entreprise/", {"fichier_logo": _creer_image_test()}, format="multipart")
    reponse = client.patch("/api/v1/entreprise/", {"retirer_logo": True}, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["logo"] == ""
    assert reponse.data["logo_1x"] == ""
    assert reponse.data["logo_original"] == ""

    with schema_context("public"):
        entreprise = Entreprise.objects.get(schema_name=SCHEMA)
        assert entreprise.logo == ""
        assert entreprise.logo_1x == ""
        assert entreprise.logo_original == ""
