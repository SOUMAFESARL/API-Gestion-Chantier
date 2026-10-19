"""Tests de calcul de durée calendaire et ouvrée de projet (lots E1 et E2)."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet
from apps.projets.serializers import DureeProjetSerializer, ProjetSerializer
from apps.projets.services.durees import decaler_mois, duree_calendaire
from apps.tiers.models import Tiers


def test_duree_calendaire_annee_pleine():
    """duree_calendaire(2026-01-01, 2026-12-31) rend annees=1, mois=0, jours=0."""
    res = duree_calendaire(date(2026, 1, 1), date(2026, 12, 31))
    assert res == {"annees": 1, "mois": 0, "jours": 0}

    # Supporte également les chaînes ISO
    res_str = duree_calendaire("2026-01-01", "2026-12-31")
    assert res_str == {"annees": 1, "mois": 0, "jours": 0}


def test_duree_calendaire_fin_fevrier():
    """duree_calendaire(2026-01-31, 2026-02-28) rend annees=0, mois=1, jours=1."""
    res = duree_calendaire(date(2026, 1, 31), date(2026, 2, 28))
    assert res == {"annees": 0, "mois": 1, "jours": 1}

    res_str = duree_calendaire("2026-01-31", "2026-02-28")
    assert res_str == {"annees": 0, "mois": 1, "jours": 1}


def test_duree_calendaire_multi_annees():
    """duree_calendaire(2026-03-15, 2028-06-14) rend annees=2, mois=3, jours=0."""
    res = duree_calendaire(date(2026, 3, 15), date(2028, 6, 14))
    assert res == {"annees": 2, "mois": 3, "jours": 0}

    res_str = duree_calendaire("2026-03-15", "2028-06-14")
    assert res_str == {"annees": 2, "mois": 3, "jours": 0}


def test_duree_calendaire_meme_jour():
    """duree_calendaire(2026-10-19, 2026-10-19) rend annees=0, mois=0, jours=1."""
    res = duree_calendaire(date(2026, 10, 19), date(2026, 10, 19))
    assert res == {"annees": 0, "mois": 0, "jours": 1}

    res_str = duree_calendaire("2026-10-19", "2026-10-19")
    assert res_str == {"annees": 0, "mois": 0, "jours": 1}


def test_duree_calendaire_mois_et_jours():
    """duree_calendaire(2025-02-03, 2025-07-15) rend annees=0, mois=5, jours=13."""
    res = duree_calendaire(date(2025, 2, 3), date(2025, 7, 15))
    assert res == {"annees": 0, "mois": 5, "jours": 13}

    res_str = duree_calendaire("2025-02-03", "2025-07-15")
    assert res_str == {"annees": 0, "mois": 5, "jours": 13}


def test_duree_calendaire_date_manquante_ou_fin_anterieure():
    """Rend None si une date manque ou si la fin précède le début."""
    assert duree_calendaire(None, date(2026, 1, 1)) is None
    assert duree_calendaire(date(2026, 1, 1), None) is None
    assert duree_calendaire(None, None) is None
    assert duree_calendaire(date(2026, 1, 2), date(2026, 1, 1)) is None
    assert duree_calendaire("2026-01-02", "2026-01-01") is None


def test_projet_propriete_duree_calendaire():
    """Projet.duree_calendaire expose les quatre clés, jours_ouvres égal à duree_jours_ouvres."""
    projet = Projet(
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    res = projet.duree_calendaire
    assert res is not None
    assert set(res.keys()) == {"annees", "mois", "jours", "jours_ouvres"}
    assert res["annees"] == 1
    assert res["mois"] == 0
    assert res["jours"] == 0
    assert res["jours_ouvres"] == projet.duree_jours_ouvres
    assert isinstance(res["jours_ouvres"], int)


def test_projet_propriete_duree_calendaire_dates_manquantes_ou_incoherentes():
    """Projet.duree_calendaire rend None si dates manquantes ou incohérentes."""
    p_sans_debut = Projet(date_debut_prevue=None, date_fin_prevue=date(2026, 12, 31))
    assert p_sans_debut.duree_calendaire is None

    p_sans_fin = Projet(date_debut_prevue=date(2026, 1, 1), date_fin_prevue=None)
    assert p_sans_fin.duree_calendaire is None

    p_incoherent = Projet(
        date_debut_prevue=date(2026, 12, 31),
        date_fin_prevue=date(2026, 1, 1),
    )
    assert p_incoherent.duree_calendaire is None


def test_decaler_mois():
    """Vérifie le décalage de mois avec ajustement au dernier jour du mois."""
    assert decaler_mois(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert decaler_mois(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert decaler_mois(date(2026, 8, 31), 1) == date(2026, 9, 30)


@pytest.fixture
def client_api(schema_demo):
    """Client API authentifié en tant qu'administrateur dans le schéma tenant demo."""
    admin, _ = Utilisateur.objects.get_or_create(
        email="admin.duree@demo.ci",
        defaults={
            "password": "Test12345!",
            "nom": "Admin",
            "role_global": RoleGlobal.ADMIN,
            "statut": StatutUtilisateur.ACTIF,
        },
    )
    if not admin.has_usable_password():
        admin.set_password("Test12345!")
        admin.save()
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(admin)
    return client


@pytest.mark.django_db
def test_api_projet_detail_duree_calendaire(client_api):
    """GET du détail d'un projet daté rend duree et duree_jours_ouvres."""
    tiers = Tiers.objects.create(
        raison_sociale="Client Test Durée",
        type_tiers="ENTREPRISE",
    )
    projet = Projet.objects.create(
        reference="PRJ-DUR-001",
        nom="Projet Durée Test",
        client=tiers,
        maitre_ouvrage="Client Test Durée",
        ville="Abidjan",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    url = f"/api/v1/projets/{projet.pk}/"
    response = client_api.get(url)
    assert response.status_code == 200

    data = response.data
    assert "duree_jours_ouvres" in data
    assert data["duree_jours_ouvres"] == projet.duree_jours_ouvres
    assert "duree" in data
    assert data["duree"] == {
        "annees": 1,
        "mois": 0,
        "jours": 0,
        "jours_ouvres": data["duree_jours_ouvres"],
    }


@pytest.mark.django_db
def test_api_projet_detail_duree_null_si_dates_absentes(client_api):
    """duree vaut null quand date_debut_prevue ou date_fin_prevue est absente."""
    tiers = Tiers.objects.create(
        raison_sociale="Client Test Sans Dates",
        type_tiers="ENTREPRISE",
    )
    projet = Projet.objects.create(
        reference="PRJ-DUR-002",
        nom="Projet Sans Dates",
        client=tiers,
        maitre_ouvrage="Client Test Sans Dates",
        ville="Abidjan",
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    url = f"/api/v1/projets/{projet.pk}/"
    response = client_api.get(url)
    assert response.status_code == 200
    assert response.data["duree"] is None
    assert response.data["duree_jours_ouvres"] is None

    # Date de début seule
    projet.date_debut_prevue = date(2026, 1, 1)
    projet.save()
    response = client_api.get(url)
    assert response.status_code == 200
    assert response.data["duree"] is None
    assert response.data["duree_jours_ouvres"] is None

    # Date de fin seule
    projet.date_debut_prevue = None
    projet.date_fin_prevue = date(2026, 12, 31)
    projet.save()
    response = client_api.get(url)
    assert response.status_code == 200
    assert response.data["duree"] is None
    assert response.data["duree_jours_ouvres"] is None


@pytest.mark.django_db
def test_api_patch_projet_duree_lecture_seule(client_api):
    """duree est en lecture seule : un PATCH ne change rien et ne lève pas d'erreur."""
    tiers = Tiers.objects.create(
        raison_sociale="Client Test Patch",
        type_tiers="ENTREPRISE",
    )
    projet = Projet.objects.create(
        reference="PRJ-DUR-003",
        nom="Projet Test Patch",
        client=tiers,
        maitre_ouvrage="Client Test Patch",
        ville="Abidjan",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    url = f"/api/v1/projets/{projet.pk}/"
    valeur_initiale_jours_ouvres = projet.duree_jours_ouvres
    duree_attendue = {
        "annees": 1,
        "mois": 0,
        "jours": 0,
        "jours_ouvres": valeur_initiale_jours_ouvres,
    }

    # Envoi de fausses valeurs de duree dans le PATCH
    response = client_api.patch(
        url,
        {
            "duree": {
                "annees": 99,
                "mois": 11,
                "jours": 28,
                "jours_ouvres": 999,
            }
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["duree"] == duree_attendue
    assert response.data["duree_jours_ouvres"] == valeur_initiale_jours_ouvres

    # Envoi de duree null dans le PATCH
    response_null = client_api.patch(url, {"duree": None}, format="json")
    assert response_null.status_code == 200
    assert response_null.data["duree"] == duree_attendue
    assert response_null.data["duree_jours_ouvres"] == valeur_initiale_jours_ouvres

    # Le projet en base reste intact
    projet.refresh_from_db()
    assert projet.duree_calendaire == duree_attendue
    assert projet.duree_jours_ouvres == valeur_initiale_jours_ouvres


def test_duree_projet_serializer():
    """DureeProjetSerializer sérialise un dictionnaire contenant les quatre clés."""
    payload = {"annees": 1, "mois": 2, "jours": 3, "jours_ouvres": 250}
    serializer = DureeProjetSerializer(payload)
    assert serializer.data == payload


@pytest.mark.django_db
def test_projet_serializer_expose_duree(schema_demo):
    """ProjetSerializer inclut le champ duree calculé depuis Projet.duree_calendaire."""
    tiers = Tiers.objects.create(
        raison_sociale="Client Serializer Test",
        type_tiers="ENTREPRISE",
    )
    projet = Projet.objects.create(
        reference="PRJ-SER-001",
        nom="Projet Serializer Test",
        client=tiers,
        maitre_ouvrage="Client Serializer Test",
        ville="Abidjan",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    data = ProjetSerializer(projet).data
    assert "duree" in data
    assert "duree_jours_ouvres" in data
    assert data["duree"] == {
        "annees": 1,
        "mois": 0,
        "jours": 0,
        "jours_ouvres": projet.duree_jours_ouvres,
    }

    projet_sans_date = Projet.objects.create(
        reference="PRJ-SER-002",
        nom="Projet Sans Date Test",
        client=tiers,
        maitre_ouvrage="Client Serializer Test",
        ville="Abidjan",
        date_debut_prevue=None,
        date_fin_prevue=None,
    )
    data_sans_date = ProjetSerializer(projet_sans_date).data
    assert "duree" in data_sans_date
    assert data_sans_date["duree"] is None
