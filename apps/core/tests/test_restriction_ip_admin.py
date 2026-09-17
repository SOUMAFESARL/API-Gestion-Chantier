"""Tests de sécurité : verrouillage de l'accès au panneau d'administration par IP.

US-023 / T-043 :
- GIVEN /admin/dashboard/ WHEN accessible depuis une IP non autorisée THEN 403
- GIVEN /admin/ WHEN accessible depuis un sous-domaine client (tenant) THEN 403
- Support des masques de sous-réseau CIDR
- Réponses 403 adaptées (HTML pour navigateur, JSON pour API)
- Traçabilité dans les journaux de sécurité
"""

import json
import logging
from unittest.mock import patch

import pytest
from django.test.utils import override_settings
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def cache_vide():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_admin_dashboard_refuse_ip_hors_whitelist():
    """Critère d'acceptation direct US-023 :
    GIVEN /admin/dashboard/ WHEN accessible depuis une IP non autorisée THEN 403.
    """
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.25")

    with override_settings(SUPER_ADMIN_IPS=["192.168.1.10"], DEBUG=False):
        reponse = client.get("/admin/dashboard/")

    assert reponse.status_code == 403
    assert b"Acc\xc3\xa8s Restreint" in reponse.content or b"acces_refuse" in reponse.content


@pytest.mark.django_db
def test_admin_refuse_ip_hors_whitelist_reponse_html():
    """Une tentative de consultation Web sur /admin/ depuis une IP non autorisée
    reçoit une page HTML 403 neutre ne dévoilant aucune information sur l'admin.
    """
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.99")

    with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"], DEBUG=False):
        reponse = client.get("/admin/", HTTP_ACCEPT="text/html,application/xhtml+xml")

    assert reponse.status_code == 403
    assert "text/html" in reponse.headers.get("Content-Type", "")
    assert "Accès Restreint (403)" in reponse.content.decode("utf-8")


@pytest.mark.django_db
def test_admin_refuse_ip_hors_whitelist_reponse_json():
    """Une requête API (Accept: application/json) rejetée reçoit un format d'erreur JSON standardisé."""
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.99")

    with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"], DEBUG=False):
        reponse = client.get("/admin/", HTTP_ACCEPT="application/json")

    assert reponse.status_code == 403
    assert "application/json" in reponse.headers.get("Content-Type", "")
    donnees = json.loads(reponse.content)
    assert donnees["erreur"]["code"] == "acces_refuse"


@pytest.mark.django_db
def test_admin_autorise_ip_exacte():
    """Une adresse IP figurant explicitement dans SUPER_ADMIN_IPS est autorisée."""
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="192.0.2.15")

    with override_settings(SUPER_ADMIN_IPS=["192.0.2.15"], DEBUG=False):
        reponse = client.get("/admin/")

    # L'accès franchit le middleware et atteint Django admin (302 vers login ou 200)
    assert reponse.status_code in (200, 302)


@pytest.mark.django_db
def test_admin_autorise_plage_cidr():
    """Une adresse IP comprise dans un sous-réseau CIDR (ex: 192.168.1.0/24) est autorisée."""
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="192.168.1.42")

    with override_settings(SUPER_ADMIN_IPS=["192.168.1.0/24"], DEBUG=False):
        reponse = client.get("/admin/")

    assert reponse.status_code in (200, 302)


@pytest.mark.django_db
def test_admin_autorise_avec_x_forwarded_for():
    """L'IP d'origine transmise dans HTTP_X_FORWARDED_FOR est correctement évaluée."""
    client = APIClient(
        headers={"host": "localhost"},
        REMOTE_ADDR="127.0.0.1",  # IP du reverse proxy local
        HTTP_X_FORWARDED_FOR="192.168.1.88, 10.0.0.1",
    )

    with override_settings(SUPER_ADMIN_IPS=["192.168.1.0/24"], DEBUG=False):
        reponse = client.get("/admin/")

    assert reponse.status_code in (200, 302)


@pytest.mark.django_db
def test_admin_interdit_sur_sous_domaine_tenant():
    """L'accès à /admin/ est strictement interdit sur les sous-domaines clients (tenants),
    même si l'adresse IP est dans la liste blanche.
    """
    client = APIClient(headers={"host": "demo.localhost"}, REMOTE_ADDR="127.0.0.1")

    with override_settings(SUPER_ADMIN_IPS=["127.0.0.1"], DEBUG=False):
        reponse = client.get("/admin/")

    assert reponse.status_code == 403


@pytest.mark.django_db
def test_super_admin_verifier_acces_endpoint():
    """L'endpoint /api/v1/super-admin/verifier-acces/ valide dynamiquement l'autorisation IP."""
    url = "/api/v1/super-admin/verifier-acces/"

    # 1. IP non autorisée
    client_refuse = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.1")
    with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"], DEBUG=False):
        rep_refus = client_refuse.get(url)
    assert rep_refus.status_code == 403
    assert rep_refus.json()["erreur"]["code"] == "acces_refuse"

    # 2. IP autorisée
    client_ok = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="10.0.0.1")
    with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"], DEBUG=False):
        rep_ok = client_ok.get(url)
    assert rep_ok.status_code == 200
    assert rep_ok.json()["statut"] == "autorise"
    assert rep_ok.json()["ip"] == "10.0.0.1"


@pytest.mark.django_db
def test_journalisation_securite_sur_rejet(caplog):
    """Toute tentative rejetée émet un avertissement dans le logger securite.super_admin."""
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="203.0.113.77")

    with caplog.at_level(logging.WARNING, logger="securite.super_admin"):
        with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"], DEBUG=False):
            client.get("/admin/dashboard/")

    assert any(
        "Tentative d'accès non autorisée au panneau d'administration" in record.message
        and "203.0.113.77" in record.message
        for record in caplog.records
    )
