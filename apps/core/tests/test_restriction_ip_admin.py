"""Tests de sécurité : absence de restriction d'adresse IP sur la plateforme.

Vérifie que :
- L'administration (/admin/, /admin/dashboard/) n'est pas bloquée par adresse IP
- L'endpoint de vérification d'accès Super Admin autorise systématiquement
- La fonction est_ip_autorisee renvoie toujours True
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.ip_restriction import est_ip_autorisee


@pytest.fixture(autouse=True)
def cache_vide():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_admin_dashboard_sans_restriction_ip():
    """L'accès à /admin/dashboard/ renvoie 404 par défaut (Django admin désactivé)."""
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.25")
    reponse = client.get("/admin/dashboard/")
    assert reponse.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_sans_restriction_ip():
    """L'accès à /admin/ renvoie 404 par défaut (Django admin désactivé)."""
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.99")
    reponse = client.get("/admin/")
    assert reponse.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_super_admin_verifier_acces_endpoint():
    """L'endpoint /api/v1/super-admin/verifier-acces/ autorise l'accès quelle que soit l'IP."""
    url = "/api/v1/super-admin/verifier-acces/"
    client = APIClient(headers={"host": "localhost"}, REMOTE_ADDR="198.51.100.1")
    reponse = client.get(url)
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.json()["statut"] == "autorise"


def test_est_ip_autorisee_retourne_toujours_vrai():
    """est_ip_autorisee autorise toutes les adresses IP sans exception."""
    assert est_ip_autorisee("127.0.0.1") is True
    assert est_ip_autorisee("198.51.100.42") is True
    assert est_ip_autorisee("") is True

