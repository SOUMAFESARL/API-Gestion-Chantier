"""Factures d'abonnement : parcours paiement, isolation et export PDF."""

from io import BytesIO

import pytest
from django_tenants.utils import schema_context
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.billing.models import Facture, Plan
from apps.billing.services.paiement import PaiementAbonnementService
from apps.billing.tests.test_cinetpay import entreprise_et_admin  # noqa: F401
from apps.core.enums import RoleGlobal
from apps.tenants.models import Entreprise

pytestmark = pytest.mark.django_db


@pytest.fixture
def facture_api(entreprise_et_admin, settings):  # noqa: F811
    settings.FACTURATION_EMETTEUR = {"raison_sociale": "Editeur Test", "rccm": "TEST-123"}
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(entreprise_et_admin["admin"])
    response = client.post(
        "/api/v1/cinetpay/initier/",
        {
            "plan_code": Plan.Code.MAITRE_OEUVRE,
            "cycle": "MENSUEL",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    return client, response.data, entreprise_et_admin


def test_facture_creee_et_pdf(facture_api):
    client, paiement, _ = facture_api
    response = client.get(paiement["facture_url"])
    assert response.status_code == 200
    facture = response.json()
    assert facture["statut"] == "EMISE"
    assert facture["montant_ht"] + facture["montant_tva"] == facture["montant_ttc"]
    assert facture["devise"] == "XOF"
    assert "charge_utile" not in facture["paiements"][0]
    liste = client.get("/api/v1/factures/").json()
    assert liste["total"] == 1
    assert liste["resultats"][0]["numero"] == paiement["numero_facture"]
    pdf = client.get(paiement["facture_pdf_url"])
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf["Cache-Control"] == "private, no-store"
    assert pdf.content.startswith(b"%PDF-")
    texte = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert paiement["numero_facture"] in texte
    assert "Editeur Test" in texte
    assert "TOTAL TTC" in texte


def test_facture_payee_et_webhook_rejoue(facture_api):
    client, paiement, _ = facture_api
    for _ in range(2):
        PaiementAbonnementService.traiter_notification_webhook(paiement["transaction_id"])
    response = client.get(paiement["facture_url"])
    assert response.json()["statut"] == "PAYEE"
    assert response.json()["paiements"][0]["paye_le"]
    assert client.get("/api/v1/factures/?statut=PAYEE").json()["total"] == 1
    assert client.get("/api/v1/factures/?statut=EMISE").json()["total"] == 0


def test_archive_ne_change_pas(facture_api, settings):
    client, paiement, contexte = facture_api
    avant = client.get(paiement["facture_url"]).json()["contexte_facturation"]
    with schema_context("public"):
        Entreprise.objects.filter(pk=contexte["entreprise"].pk).update(raison_sociale="Nouveau nom")
        Plan.objects.filter(code=Plan.Code.MAITRE_OEUVRE).update(libelle="Nouveau forfait")
    settings.FACTURATION_EMETTEUR = {"raison_sociale": "Autre editeur"}
    apres = client.get(paiement["facture_url"]).json()["contexte_facturation"]
    assert avant == apres


@pytest.mark.parametrize("suffixe", ["", "pdf/"])
def test_autre_entreprise_inaccessible(facture_api, suffixe):
    client, paiement, _ = facture_api
    with schema_context("public"):
        autre = Entreprise.objects.get(schema_name="public")
        Facture.objects.filter(pk=paiement["facture_id"]).update(entreprise=autre)
    assert client.get(paiement["facture_url"] + suffixe).status_code == 404
    assert client.get("/api/v1/factures/").json()["total"] == 0


def test_anonyme_et_role_refuses(facture_api):
    client, paiement, contexte = facture_api
    client.force_authenticate(user=None)
    assert client.get(paiement["facture_url"]).status_code == 401
    contexte["admin"].role_global = RoleGlobal.CHEF_PROJET
    client.force_authenticate(contexte["admin"])
    assert client.get(paiement["facture_url"]).status_code == 403
    assert client.get(paiement["facture_pdf_url"]).status_code == 403


def test_schema_public_refuse(facture_api):
    _, paiement, contexte = facture_api
    client = APIClient(headers={"host": "localhost"})
    client.force_authenticate(contexte["admin"])
    assert client.get(paiement["facture_url"]).status_code == 403


def test_statut_invalide_et_ecriture_refuses(facture_api):
    client, paiement, _ = facture_api
    assert client.get("/api/v1/factures/?statut=INCONNU").status_code == 400
    assert client.post("/api/v1/factures/", {}).status_code == 405
    assert client.delete(paiement["facture_url"]).status_code == 405


def test_facture_historique_sans_contexte(facture_api):
    client, paiement, _ = facture_api
    with schema_context("public"):
        Facture.objects.filter(pk=paiement["facture_id"]).update(contexte_facturation={})
    pdf = client.get(paiement["facture_pdf_url"])
    assert pdf.status_code == 200
    texte = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "coordonnees non archivees" in texte
