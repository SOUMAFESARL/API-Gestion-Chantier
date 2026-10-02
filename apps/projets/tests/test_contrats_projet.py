"""Real multipart CRUD, private downloads, validation and storage compensation."""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context
from drf_spectacular.generators import SchemaGenerator
from PIL import Image
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet, ProjetContrat
from apps.projets.services.contrats import MAX_FICHIER
from apps.projets.storage import StockageContrats
from apps.tenants.models import Domaine, Entreprise

pytestmark = pytest.mark.django_db


def formulaire():
    return {
        "nom": "Projet contrats",
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Man",
        "maitre_ouvrage": "sglaq",
    }


def document(extension="pdf", name=None):
    stream = io.BytesIO()
    if extension.lower() == "pdf":
        pdf = canvas.Canvas(stream)
        pdf.drawString(20, 750, "Contrat projet")
        pdf.save()
        mime = "application/pdf"
    else:
        fmt = "PNG" if extension.lower() == "png" else "JPEG"
        Image.new("RGB", (12, 12), "white").save(stream, format=fmt)
        mime = "image/png" if fmt == "PNG" else "image/jpeg"
    return SimpleUploadedFile(name or f"contrat.{extension}", stream.getvalue(), content_type=mime)


@pytest.fixture
def contexte(schema_demo, settings, tmp_path):
    settings.PROJET_CONTRATS_ROOT = str(tmp_path / "contrats")
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    admin = Utilisateur.objects.create_user(
        email="contrats.direction@demo.ci",
        nom="Direction",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    externe = Utilisateur.objects.create_user(
        email="contrats.externe@demo.ci",
        nom="Externe",
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(admin)
    return client, admin, externe, Path(settings.PROJET_CONTRATS_ROOT)


def test_multiple_contracts_creation_list_detail_and_download(contexte):
    client, admin, _, root = contexte
    pdf, png = document(), document("png")
    pdf_bytes = pdf.read()
    pdf.seek(0)
    created = client.post(
        "/api/v1/projets/", {**formulaire(), "contrat": [pdf, png]}, format="multipart"
    )
    assert created.status_code == 201, created.data
    assert len(created.data["contrat"]) == 2
    assert [row["type_contenu"] for row in created.data["contrat"]] == [
        "application/pdf",
        "image/png",
    ]
    projet = Projet.objects.get(reference=created.data["reference"])
    assert all(row.cree_par_id == admin.pk for row in projet.contrats.all())
    assert all(
        row.fichier.name.startswith(f"demo/projets/{projet.pk}/") for row in projet.contrats.all()
    )
    assert len(list(root.rglob("*.pdf"))) == 1
    assert client.get(created["Location"]).data == created.data
    assert client.get("/api/v1/projets/").data[0]["contrat"] == created.data["contrat"]
    response = client.get(created.data["contrat"][0]["url"])
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert response["Cache-Control"] == "private, no-store"
    assert b"".join(response.streaming_content) == pdf_bytes
    response.close()


@pytest.mark.parametrize("extension", ["pdf", "jpg", "jpeg", "png", "jepg", "JPG"])
def test_allowed_formats(contexte, extension):
    client, *_ = contexte
    created = client.post(
        "/api/v1/projets/", {**formulaire(), "contrat": [document(extension)]}, format="multipart"
    )
    assert created.status_code == 201, created.data
    assert len(created.data["contrat"]) == 1
    download = client.get(created.data["contrat"][0]["url"])
    assert download.status_code == 200
    assert download["Content-Type"] == created.data["contrat"][0]["type_contenu"]
    assert b"".join(download.streaming_content)
    download.close()


@pytest.mark.parametrize("method", ["put", "patch"])
def test_add_multiple_and_keep_existing_contracts(contexte, method):
    client, *_ = contexte
    created = client.post(
        "/api/v1/projets/", {**formulaire(), "contrat": [document()]}, format="multipart"
    )
    assert created.status_code == 201
    data = formulaire() if method == "put" else {}
    updated = getattr(client, method)(
        created["Location"],
        {
            **data,
            "contrat": [document("jpg"), document("png")],
        },
        format="multipart",
    )
    assert updated.status_code == 200, updated.data
    assert len(updated.data["contrat"]) == 3
    assert updated.data["contrat"][0]["id"] == created.data["contrat"][0]["id"]
    no_upload = getattr(client, method)(
        created["Location"], {**formulaire(), "contrat": []}, format="json"
    )
    assert no_upload.status_code == 200
    assert no_upload.data["contrat"] == updated.data["contrat"]


@pytest.mark.parametrize(
    "name,content",
    [
        ("contrat.exe", b"arbitrary"),
        ("contrat.pdf", b"fake PDF"),
        ("contrat.png", b"fake PNG"),
        ("contrat.jpeg", b"fake JPEG"),
        ("contrat.pdf", b"%PDF-1.7\ninvalid\n%%EOF"),
        ("contrat.pdf", b""),
    ],
)
def test_invalid_batch_does_not_create_project_or_files(contexte, name, content):
    client, _, _, root = contexte
    response = client.post(
        "/api/v1/projets/",
        {
            **formulaire(),
            "contrat": [
                document(),
                SimpleUploadedFile(name, content, content_type="application/pdf"),
            ],
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert not Projet.objects.exists() and not ProjetContrat.objects.exists()
    assert not root.exists()


def test_image_content_must_match_extension(contexte):
    client, *_ = contexte
    response = client.post(
        "/api/v1/projets/",
        {
            **formulaire(),
            "contrat": [document("png", name="contrat.jpg")],
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert not Projet.objects.exists()


def test_file_count_and_size_limits(contexte):
    client, *_ = contexte
    too_many = client.post(
        "/api/v1/projets/",
        {
            **formulaire(),
            "contrat": [document() for _ in range(11)],
        },
        format="multipart",
    )
    assert too_many.status_code == 400
    large = SimpleUploadedFile("contrat.pdf", b"%PDF-" + b"x" * MAX_FICHIER)
    response = client.post(
        "/api/v1/projets/", {**formulaire(), "contrat": [large]}, format="multipart"
    )
    assert response.status_code == 400
    assert not Projet.objects.exists()


def test_total_batch_size_limit(contexte):
    # Valid content remains unchanged; simulate already-measured upload sizes.
    fichiers = [document() for _ in range(6)]
    for fichier in fichiers:
        fichier.size = MAX_FICHIER
    from apps.projets.serializers.swagger import ProjetPostSerializer

    serializer = ProjetPostSerializer(data={**formulaire(), "contrat": fichiers})
    assert not serializer.is_valid()
    assert "50 Mo" in str(serializer.errors)
    assert not Projet.objects.exists()


@pytest.mark.parametrize("method", ["post", "patch"])
def test_storage_error_rolls_back_database_and_written_files(contexte, method):
    client, _, _, root = contexte
    url = "/api/v1/projets/"
    if method == "patch":
        initial = client.post(url, formulaire(), format="json")
        assert initial.status_code == 201
        url = initial["Location"]
    save = StockageContrats._save
    calls = []

    def write_then_fail(storage, name, content):
        calls.append(name)
        if len(calls) == 2:
            raise OSError("Storage unavailable")
        return save(storage, name, content)

    data = {**formulaire(), "nom": "Do not persist", "contrat": [document(), document("png")]}
    with patch.object(StockageContrats, "_save", write_then_fail):
        response = getattr(client, method)(url, data, format="multipart")
    assert response.status_code == 500
    assert not Projet.objects.filter(nom="Do not persist").exists()
    assert not ProjetContrat.objects.exists()
    assert not [path for path in root.rglob("*") if path.is_file()]
    if method == "patch":
        assert client.get(url).data["nom"] == formulaire()["nom"]


def test_download_requires_project_permission_and_deleted_project_is_hidden(contexte):
    client, admin, externe, root = contexte
    created = client.post(
        "/api/v1/projets/", {**formulaire(), "contrat": [document()]}, format="multipart"
    )
    assert created.status_code == 201
    url = created.data["contrat"][0]["url"]
    client.force_authenticate(None)
    assert client.get(url).status_code == 401
    client.force_authenticate(externe)
    assert client.get(url).status_code == 403
    client.force_authenticate(admin)
    other = client.post("/api/v1/projets/", formulaire(), format="json")
    assert (
        client.get(other["Location"] + "?contrat=" + created.data["contrat"][0]["id"]).status_code
        == 404
    )
    assert client.get(created["Location"] + "?contrat=bad-id").status_code == 400
    assert client.delete(created["Location"]).status_code == 204
    assert client.get(url).status_code == 404
    assert len(list(root.rglob("*.pdf"))) == 1


def test_json_without_upload_and_json_urls_are_not_uploads(contexte):
    client, *_ = contexte
    created = client.post("/api/v1/projets/", formulaire(), format="json")
    assert created.status_code == 201
    assert created.data["contrat"] == []
    response = client.patch(
        created["Location"], {"contrat": ["https://example.com/fake.pdf"]}, format="json"
    )
    assert response.status_code == 400
    assert not ProjetContrat.objects.exists()


def test_list_contracts_are_prefetched(contexte):
    client, *_ = contexte
    for _ in range(3):
        assert (
            client.post(
                "/api/v1/projets/", {**formulaire(), "contrat": [document()]}, format="multipart"
            ).status_code
            == 201
        )
    with CaptureQueriesContext(connection) as queries:
        listed = client.get("/api/v1/projets/")
    assert listed.status_code == 200
    selects = [q for q in queries.captured_queries if 'FROM "projet_contrat"' in q["sql"]]
    assert len(selects) == 1


def test_swagger_documents_binary_array_and_download(contexte):
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    paths = schema["paths"]
    for path, method in [
        ("/api/v1/projets/", "post"),
        ("/api/v1/projets/{id}/", "put"),
        ("/api/v1/projets/{id}/", "patch"),
    ]:
        content = paths[path][method]["requestBody"]["content"]
        assert "multipart/form-data" in content
        ref = content["multipart/form-data"]["schema"]["$ref"].rsplit("/", 1)[-1]
        contrat = schema["components"]["schemas"][ref]["properties"]["contrat"]
        assert contrat["type"] == "array"
        assert contrat["items"] == {"type": "string", "format": "binary"}
    detail = paths["/api/v1/projets/{id}/"]["get"]
    assert any(p["name"] == "contrat" and p["in"] == "query" for p in detail["parameters"])
    assert "application/pdf" in detail["responses"]["200"]["content"]


def test_contract_isolation_between_tenants_even_with_same_project_id(contexte):
    client, _, _, root = contexte
    created = client.post(
        "/api/v1/projets/",
        {
            **formulaire(),
            "contrat": [document()],
        },
        format="multipart",
    )
    assert created.status_code == 201
    projet = Projet.objects.get(reference=created.data["reference"])
    with schema_context("public"):
        tenant = Entreprise(
            schema_name="contrats_autre",
            raison_sociale="Autre entreprise",
            email_contact="autre.contrats@example.com",
        )
        tenant.save(verbosity=0)
        Domaine.objects.create(domain="contrats-autre.localhost", tenant=tenant)
    with schema_context(tenant.schema_name):
        other_admin = Utilisateur.objects.create_user(
            email="autre.admin.contrats@example.com",
            nom="Admin",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        Projet.objects.create(id=projet.pk, reference=projet.reference, **formulaire())
    other_client = APIClient(HTTP_HOST="contrats-autre.localhost")
    other_client.force_authenticate(other_admin)
    path = f"/api/v1/projets/{projet.pk}/"
    refused = other_client.get(path + "?contrat=" + created.data["contrat"][0]["id"])
    assert refused.status_code == 404
    updated = other_client.patch(path, {"contrat": [document("png")]}, format="multipart")
    assert updated.status_code == 200, updated.data
    assert len(updated.data["contrat"]) == 1
    with schema_context(tenant.schema_name):
        assert ProjetContrat.objects.get().fichier.name.startswith("contrats_autre/")
    with schema_context("demo"):
        assert ProjetContrat.objects.get().fichier.name.startswith("demo/")
    assert len(list(root.rglob("*.pdf"))) == 1
    assert len(list(root.rglob("*.png"))) == 1


def test_database_insert_failure_cleans_saved_file(contexte):
    client, _, _, root = contexte
    with patch.object(ProjetContrat, "save", side_effect=RuntimeError("Insert failed")):
        response = client.post(
            "/api/v1/projets/",
            {
                **formulaire(),
                "contrat": [document()],
            },
            format="multipart",
        )
    assert response.status_code == 500
    assert not Projet.objects.exists() and not ProjetContrat.objects.exists()
    assert not [path for path in root.rglob("*") if path.is_file()]
