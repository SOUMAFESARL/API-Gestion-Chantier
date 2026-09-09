"""Tests pour ProjetDetailView et TiersDetailView."""

from datetime import date, timedelta

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        from apps.accounts.models import Invitation

        Invitation.objects.all().delete()
        Utilisateur.tous_objets.filter(email="admin.projet@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.projet@demo.ci",
            password=MOT_DE_PASSE,
            nom="Admin",
            prenom="Projet",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        yield admin
        Invitation.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=admin.pk).delete()


def auth_client(client, admin_user):
    rep = client.post(
        "/api/v1/auth/token/",
        {"email": admin_user.email, "mot_de_passe": MOT_DE_PASSE, "origine": "WEB"},
        format="json",
    )
    token = rep.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_tiers_et_projet_detail_patch(client, admin_user):
    cl = auth_client(client, admin_user)

    # 1. Création initiale d'un tiers
    rep_tiers = cl.post(
        "/api/v1/tiers/",
        {
            "type_tiers": "ENTREPRISE",
            "raison_sociale": "Client Initial",
            "telephone": "0102030405",
            "roles": ["CLIENT_MOA"],
        },
        format="json",
    )
    assert rep_tiers.status_code == status.HTTP_201_CREATED
    tiers_id = rep_tiers.data["id"]

    # 2. Création d'un projet lié
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=90)
    rep_projet = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Chantier Initial",
            "client": tiers_id,
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "budget_initial_montant": 5000000000,
            "description": "Description originale",
            "chef_projet_invite": {
                "nom": "Kouassi",
                "prenom": "Yves",
                "email": "cp.initial@demo.ci",
                "telephone": "+2250700000000",
            },
        },
        format="json",
    )
    assert rep_projet.status_code == status.HTTP_201_CREATED
    projet_id = rep_projet.data["id"]
    reference = rep_projet.data["reference"]

    # 3. Modification partielle du tiers (PATCH)
    rep_patch_tiers = cl.patch(
        f"/api/v1/tiers/{tiers_id}/",
        {"raison_sociale": "Client Modifié", "telephone": "0708091011"},
        format="json",
    )
    assert rep_patch_tiers.status_code == status.HTTP_200_OK
    assert rep_patch_tiers.data["raison_sociale"] == "Client Modifié"
    assert rep_patch_tiers.data["telephone"] == "0708091011"

    # 4. Modification partielle du projet (PATCH)
    rep_patch_projet = cl.patch(
        f"/api/v1/projets/{projet_id}/",
        {"nom": "Chantier Modifié", "ville": "Bouaké"},
        format="json",
    )
    assert rep_patch_projet.status_code == status.HTTP_200_OK
    assert rep_patch_projet.data["nom"] == "Chantier Modifié"
    assert rep_patch_projet.data["ville"] == "Bouaké"
    assert rep_patch_projet.data["reference"] == reference
