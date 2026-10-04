"""Tests automatisés pour le service et les endpoints de nettoyage propre d'entreprises."""

from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client, override_settings

from apps.tenants.models import Entreprise
from apps.tenants.services.nettoyage import (
    SCHEMAS_PROTEGES,
    lister_entreprises_avec_directeurs,
    supprimer_entreprise_proprement,
)


@pytest.mark.django_db
def test_protection_schemas_proteges():
    """Vérifie que 'public' et 'demo' refusent catégoriquement toute suppression."""
    for schema in SCHEMAS_PROTEGES:
        with pytest.raises(ValueError, match="Suppression interdite"):
            supprimer_entreprise_proprement(schema)


@pytest.mark.django_db
def test_lister_entreprises_service():
    """Vérifie que la fonction lister_entreprises_avec_directeurs renvoie la structure attendue."""
    resultat = lister_entreprises_avec_directeurs()
    assert "total_entreprises" in resultat
    assert "entreprises" in resultat
    assert "total_demandes" in resultat
    assert "demandes_inscription" in resultat
    assert isinstance(resultat["entreprises"], list)


JETON_TEST = "jeton-de-test-uniquement-pour-pytest"

URLS_MAINTENANCE = [
    ("post", "/api/v1/maintenance/migrer-bd/"),
    ("get", "/api/v1/maintenance/purger-zanf/"),
    ("post", "/api/v1/maintenance/purger-zanf/"),
    ("get", "/api/v1/maintenance/entreprises/"),
    ("post", "/api/v1/maintenance/entreprises/supprimer/"),
]


@pytest.mark.django_db
@override_settings(MAINTENANCE_TOKEN="")
@pytest.mark.parametrize(("methode", "url"), URLS_MAINTENANCE)
def test_endpoints_maintenance_eteints_sans_jeton_configure(methode, url):
    """Sans MAINTENANCE_TOKEN configuré, chaque endpoint répond 404, même avec un jeton fourni."""
    client = Client()
    resp = getattr(client, methode)(url, HTTP_X_MAINTENANCE_TOKEN="nimporte-quoi")
    assert resp.status_code == 404


def test_aucun_jeton_de_maintenance_en_dur():
    """Le code servi ne doit contenir aucun jeton littéral (le fichier est public sur cPanel)."""
    source = (Path(settings.BASE_DIR) / "config" / "urls_public.py").read_text(encoding="utf-8")
    assert "secure-token" not in source
    assert 'token != "' not in source


@pytest.mark.django_db
@override_settings(MAINTENANCE_TOKEN=JETON_TEST)
def test_endpoints_maintenance_securite():
    """Vérifie le contrôle d'accès par token sur les endpoints de maintenance."""
    client = Client()

    # Sans token -> 403
    resp_sans = client.get("/api/v1/maintenance/entreprises/")
    assert resp_sans.status_code == 403

    # Mauvais token -> 403
    resp_faux = client.get(
        "/api/v1/maintenance/entreprises/",
        HTTP_X_MAINTENANCE_TOKEN="invalide",
    )
    assert resp_faux.status_code == 403

    # Bon token -> 200
    resp_bon = client.get(
        "/api/v1/maintenance/entreprises/",
        HTTP_X_MAINTENANCE_TOKEN=JETON_TEST,
    )
    assert resp_bon.status_code == 200
    data = resp_bon.json()
    assert data["statut"] == "ok"
    assert "entreprises" in data


@pytest.mark.django_db
@override_settings(MAINTENANCE_TOKEN=JETON_TEST)
def test_endpoint_supprimer_entreprise_protegee():
    """Vérifie que l'endpoint de suppression refuse de supprimer un schéma protégé."""
    client = Client()
    resp = client.post(
        "/api/v1/maintenance/entreprises/supprimer/",
        data={"schema_name": "demo"},
        content_type="application/json",
        HTTP_X_MAINTENANCE_TOKEN=JETON_TEST,
    )
    assert resp.status_code == 400
    assert "Suppression interdite" in resp.json().get("message", "")


@pytest.mark.django_db
def test_suppression_propre_complete_entreprise():
    """Vérifie qu'une entreprise créée pour le test est intégralement purgée (schéma et public)."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.tenants.models import DemandeInscription, Domaine

    schema_test = "temp_test_purge"

    # Création manuelle d'une entreprise sans déclencher les migrations lourdes
    ent = Entreprise(
        schema_name=schema_test,
        raison_sociale="Entreprise Temporaire Test",
        email_contact="test-purge@exemple.ci",
    )
    ent.auto_create_schema = False
    ent.save()

    Domaine.objects.create(
        domain=f"{schema_test}.localhost",
        tenant=ent,
        is_primary=True,
    )
    DemandeInscription.objects.create(
        email="test-purge@exemple.ci",
        raison_sociale="Entreprise Temporaire Test",
        slug_reserve=schema_test,
        entreprise=ent,
        cgu_version="1.0",
        cgu_acceptees_le=timezone.now(),
        expire_le=timezone.now() + timedelta(days=2),
    )

    # Exécuter la suppression
    rapport = supprimer_entreprise_proprement(schema_test)

    assert rapport["schema_supprime"] == schema_test
    assert not Entreprise.objects.filter(schema_name=schema_test).exists()
    assert not Domaine.objects.filter(domain=f"{schema_test}.localhost").exists()
    assert not DemandeInscription.objects.filter(slug_reserve=schema_test).exists()
