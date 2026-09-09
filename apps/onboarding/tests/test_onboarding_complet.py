"""Tests de bout en bout du cycle de configuration initiale (Wizard d'Onboarding)."""

from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "MotDePasse1!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture(autouse=True)
def cache_propre():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        from apps.accounts.models import Invitation
        from apps.onboarding.models import EtapeConfiguration, ProgressionConfiguration
        from apps.projets.models import Projet
        from apps.tiers.models import Tiers

        Invitation.objects.all().delete()
        EtapeConfiguration.objects.all().delete()
        ProgressionConfiguration.objects.all().delete()
        Projet.tous_objets.all().delete()
        Tiers.tous_objets.all().delete()
        Utilisateur.tous_objets.filter(email="admin.wizard@btp.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.wizard@btp.ci",
            password=MOT_DE_PASSE,
            nom="Konan",
            prenom="Yao",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        yield admin
        Invitation.objects.all().delete()
        EtapeConfiguration.objects.all().delete()
        ProgressionConfiguration.objects.all().delete()
        Projet.tous_objets.all().delete()
        Tiers.tous_objets.all().delete()
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
def test_wizard_cycle_complet(client, admin_user):
    """Vérifie l'enchaînement réel des 3 étapes du wizard et son récapitulatif."""
    cl = auth_client(client, admin_user)

    # 0. Lecture de la progression initiale
    rep = cl.get("/api/v1/configuration/")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data["pourcentage"] == 0

    # 1. Étape 1 : Modification du profil de l'entreprise
    rep_ent = cl.patch(
        "/api/v1/entreprise/",
        {
            "raison_sociale": "SOTRA BTP Pro",
            "ville": "Abidjan",
            "adresse": "Boulevard Valéry Giscard d'Estaing",
            "rccm": "CI-ABJ-2026-B-12345",
            "nif": "1234567A",
            "telephone_contact": "+2250700000000",
        },
        format="json",
    )
    assert rep_ent.status_code == status.HTTP_200_OK
    assert rep_ent.data["ville"] == "Abidjan"
    assert rep_ent.data["adresse"] == "Boulevard Valéry Giscard d'Estaing"

    # Validation de l'étape 1
    rep_val1 = cl.post("/api/v1/configuration/etapes/ENTREPRISE/valider/", {}, format="json")
    assert rep_val1.status_code == status.HTTP_200_OK
    assert rep_val1.data["pourcentage"] == 33

    # 2. Étape 2 : Création du client (tiers)
    rep_tiers = cl.post(
        "/api/v1/tiers/",
        {
            "type_tiers": "ENTREPRISE",
            "raison_sociale": "Ministère de la Construction",
            "telephone": "+2252720000000",
            "roles": ["CLIENT_MOA"],
        },
        format="json",
    )
    assert rep_tiers.status_code == status.HTTP_201_CREATED
    client_id = rep_tiers.data["id"]

    # Création du premier projet
    aujourdhui = date.today()
    fin_prevue = aujourdhui + timedelta(days=180)
    rep_projet = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Tour Administrative Plateau",
            "client": client_id,
            "ville": "Abidjan",
            "budget_initial_montant": 85000000000,  # 850 millions FCFA en centimes
            "date_debut_prevue": str(aujourdhui),
            "date_fin_prevue": str(fin_prevue),
            "description": "Construction d'une tour R+12",
            "chef_projet_invite": {
                "nom": "Soro",
                "prenom": "Mamadou",
                "email": "m.soro@btp-ci.com",
                "telephone": "+2250701020304",
            },
        },
        format="json",
    )
    assert rep_projet.status_code == status.HTTP_201_CREATED
    assert rep_projet.data["reference"].startswith("PRJ-")

    # Validation de l'étape 2
    rep_val2 = cl.post("/api/v1/configuration/etapes/PROJET/valider/", {}, format="json")
    assert rep_val2.status_code == status.HTTP_200_OK
    assert rep_val2.data["pourcentage"] == 67

    # 3. Étape 3 : Invitation de collaborateurs
    rep_inv = cl.post(
        "/api/v1/invitations/",
        {
            "email": "conducteur.travaux@btp.ci",
            "role_propose": "CT",
            "nom": "Koffi",
        },
        format="json",
    )
    assert rep_inv.status_code == status.HTTP_201_CREATED

    # Validation de l'étape 3
    rep_val3 = cl.post("/api/v1/configuration/etapes/EQUIPE/valider/", {}, format="json")
    assert rep_val3.status_code == status.HTTP_200_OK
    assert rep_val3.data["pourcentage"] == 100
    assert rep_val3.data["statut"] == "TERMINEE"

    # 4. Lecture du récapitulatif
    rep_recap = cl.get("/api/v1/configuration/recapitulatif/")
    assert rep_recap.status_code == status.HTTP_200_OK
    assert rep_recap.data["entreprise"]["raison_sociale"] == "SOTRA BTP Pro"
    assert rep_recap.data["projet"]["nom"] == "Tour Administrative Plateau"
    assert rep_recap.data["invitations"] >= 1


@pytest.mark.django_db
def test_rejeu_etape2_sans_duplication(client, admin_user):
    """Vérifie que la modification de l'étape 2 (retour arrière) met à jour sans dupliquer."""
    cl = auth_client(client, admin_user)

    # 0. Étape 1 : Validation préalable
    rep_val1 = cl.post("/api/v1/configuration/etapes/ENTREPRISE/valider/", {}, format="json")
    assert rep_val1.status_code == status.HTTP_200_OK

    # 1. Première création à l'étape 2
    rep_tiers = cl.post(
        "/api/v1/tiers/",
        {
            "type_tiers": "ENTREPRISE",
            "raison_sociale": "Client Initial MOA",
            "telephone": "+2252720000001",
            "roles": ["CLIENT_MOA"],
        },
        format="json",
    )
    assert rep_tiers.status_code == status.HTTP_201_CREATED
    tiers_id = rep_tiers.data["id"]

    rep_projet = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Projet Initial",
            "client": tiers_id,
            "ville": "Bouaké",
            "budget_initial_montant": 5000000000,
            "date_debut_prevue": "2026-06-01",
            "date_fin_prevue": "2026-12-31",
            "description": "Projet initial avant retouche",
            "chef_projet_invite": {
                "nom": "Kouadio",
                "prenom": "Jean",
                "email": "j.kouadio@btp-ci.com",
                "telephone": "+2250701020305",
            },
        },
        format="json",
    )
    assert rep_projet.status_code == status.HTTP_201_CREATED
    projet_id = rep_projet.data["id"]
    reference = rep_projet.data["reference"]

    # Valider étape 2 une première fois
    cl.post("/api/v1/configuration/etapes/PROJET/valider/", {}, format="json")

    with schema_context(SCHEMA):
        from apps.projets.models import Projet
        from apps.tiers.models import Tiers

        assert Tiers.objects.filter(pk=tiers_id).count() == 1
        assert Projet.objects.filter(pk=projet_id).count() == 1

    # 2. Simulation du retour sur l'étape 2 : PATCH au lieu de POST
    # (stratégie modifierPremierProjet)
    rep_patch_tiers = cl.patch(
        f"/api/v1/tiers/{tiers_id}/",
        {
            "raison_sociale": "Client Modifié MOA",
            "telephone": "+2252720000999",
        },
        format="json",
    )
    assert rep_patch_tiers.status_code == status.HTTP_200_OK
    assert rep_patch_tiers.data["raison_sociale"] == "Client Modifié MOA"

    rep_patch_projet = cl.patch(
        f"/api/v1/projets/{projet_id}/",
        {
            "nom": "Projet Modifié et Ajusté",
            "ville": "Yamoussoukro",
            "budget_initial_montant": 6000000000,
        },
        format="json",
    )
    assert rep_patch_projet.status_code == status.HTTP_200_OK
    assert rep_patch_projet.data["nom"] == "Projet Modifié et Ajusté"
    assert rep_patch_projet.data["reference"] == reference

    # Re-valider étape 2
    rep_val2 = cl.post("/api/v1/configuration/etapes/PROJET/valider/", {}, format="json")
    assert rep_val2.status_code == status.HTTP_200_OK

    # 3. Vérification de non-duplication en base de données
    with schema_context(SCHEMA):
        from apps.projets.models import Projet
        from apps.tiers.models import Tiers

        assert Tiers.objects.filter(supprime_le__isnull=True).count() == 1
        assert Projet.objects.filter(supprime_le__isnull=True).count() == 1

        projet_db = Projet.objects.get(pk=projet_id)
        assert projet_db.nom == "Projet Modifié et Ajusté"
        assert projet_db.ville == "Yamoussoukro"
        assert projet_db.client.raison_sociale == "Client Modifié MOA"
