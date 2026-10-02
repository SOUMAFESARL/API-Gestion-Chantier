"""Création authentifiée : identité serveur, isolation et atomicité."""

import uuid
from unittest.mock import patch

import pytest
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.authentification import emettre_jetons
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.projets.models import Projet
from apps.projets.serializers import ProjetCreationSerializer
from apps.projets.tests.service_helpers import creer_projet_via_service
from apps.tenants.models import Entreprise
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db
URL = "/api/v1/projets/contexte-creation/"


def client_jwt(user, schema="demo"):
    with schema_context(schema):
        tokens = emettre_jetons(user, origine="WEB")
    client = APIClient(HTTP_HOST="localhost")
    client.utilisateur_service = user
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def membres():
    with schema_context("demo"):
        resultat = {}
        for cle, role in [
            ("admin", RoleGlobal.ADMIN),
            ("cp", RoleGlobal.CHEF_PROJET),
            ("ct", RoleGlobal.CONDUCTEUR_TRAVAUX),
            ("cc", RoleGlobal.CHEF_CHANTIER),
            ("visiteur", RoleGlobal.VISITEUR),
            ("dg", RoleGlobal.DIRECTEUR_GENERAL),
        ]:
            resultat[cle] = Utilisateur.objects.create_user(
                email=f"{cle}.contexte@demo.ci",
                nom=cle,
                role_global=role,
            )
        resultat["client"] = Tiers.objects.create(
            raison_sociale="Maître ouvrage contexte",
            telephone="0102030405",
        )
        return resultat


@pytest.fixture
def payload(membres):
    return {
        "nom": "Projet identité serveur",
        "client": str(membres["client"].pk),
        "ville": "Adjamé",
        "date_debut_prevue": "2026-10-01",
        "date_fin_prevue": "2026-12-31",
        "budget_initial_montant": 200000,
        "lots": [{"libelle": "Gros œuvre"}],
        "equipe": {
            "chef_projet_id": str(membres["cp"].pk),
            "conducteur_travaux_id": str(membres["ct"].pk),
            "chefs_chantier_ids": [str(membres["cc"].pk)],
            "visiteurs_ids": [str(membres["visiteur"].pk)],
        },
    }


def test_contexte_connecte_et_choix(membres):
    with schema_context("demo"):
        inactif = Utilisateur.objects.create_user(
            email="inactif.contexte@demo.ci",
            nom="Inactif",
            statut=StatutUtilisateur.DESACTIVE,
        )
        supprime = Utilisateur.objects.create_user(
            email="supprime.contexte@demo.ci",
            nom="Supprimé",
        )
        supprime.delete()
        entreprise = Entreprise.objects.get(schema_name="demo")
    client = client_jwt(membres["admin"])
    response = client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert data["utilisateur"]["id"] == str(membres["admin"].pk)
    assert data["entreprise"]["id"] == str(entreprise.pk)
    profil = client.get("/api/v1/auth/profil/").json()
    assert data["entreprise"] == profil["entreprise"]
    collaborateurs = {u["id"]: u for u in data["collaborateurs"]}
    assert str(inactif.pk) not in collaborateurs
    assert str(supprime.pk) not in collaborateurs
    assert collaborateurs[str(membres["cp"].pk)]["assignable_responsable"] is True
    assert collaborateurs[str(membres["dg"].pk)]["assignable_responsable"] is False
    assert str(membres["client"].pk) in {c["id"] for c in data["clients"]}
    assert {r["valeur"] for r in data["roles_projet"]} == {"CP", "CT", "CC", "MOA", "MOE", "VI"}


def test_contexte_exige_authentification_et_ecriture(membres):
    assert APIClient(HTTP_HOST="demo.localhost").get(URL).status_code == 401
    assert client_jwt(membres["visiteur"]).get(URL).status_code == 403


def test_creation_refuse_identites_fournies_et_trace_auteur(membres):
    payload = {
        "nom": "Identite serveur",
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Man",
        "maitre_ouvrage": "Client",
    }
    client = client_jwt(membres["admin"])
    falsifie = {
        **payload,
        "cree_par": str(membres["visiteur"].pk),
        "utilisateur_id": str(membres["visiteur"].pk),
        "entreprise_id": str(uuid.uuid4()),
        "schema": "public",
    }
    refused = client.post("/api/v1/projets/", falsifie, format="json")
    assert refused.status_code == 400
    with schema_context("demo"):
        assert not Projet.objects.filter(nom=payload["nom"]).exists()
    response = client.post("/api/v1/projets/", payload, format="json")
    assert response.status_code == 201, response.data
    assert "cree_par" not in response.data and "entreprise" not in response.data
    with schema_context("demo"):
        projet = Projet.objects.get(reference=response.data["reference"])
        assert projet.cree_par_id == membres["admin"].pk
        assert projet.chef_projet_id is None
        assert not projet.lots.exists() and not projet.affectations.exists()
    assert client.get(response["Location"]).data == response.data


@pytest.mark.parametrize("champ", ["chefs_chantier_ids", "visiteurs_ids"])
def test_membre_inexistant_refuse_sans_creation(membres, payload, champ):
    payload["equipe"][champ] = [str(uuid.uuid4())]
    response = creer_projet_via_service(
        client_jwt(membres["admin"]), "/api/v1/projets/", payload, format="json"
    )
    assert response.status_code == 400
    with schema_context("demo"):
        assert not Projet.objects.filter(nom=payload["nom"]).exists()


def test_membre_desactive_refuse(membres, payload):
    with schema_context("demo"):
        membres["cc"].is_active = False
        membres["cc"].save()
    response = creer_projet_via_service(
        client_jwt(membres["admin"]), "/api/v1/projets/", payload, format="json"
    )
    assert response.status_code == 400


def test_roles_multiples_refuses_explicitement(membres, payload):
    payload["equipe"]["conducteur_travaux_id"] = payload["equipe"]["chef_projet_id"]
    response = creer_projet_via_service(
        client_jwt(membres["admin"]), "/api/v1/projets/", payload, format="json"
    )
    assert response.status_code == 400


def test_creation_annule_aussi_compte_invite_si_erreur(membres, payload):
    payload["equipe"].pop("chef_projet_id")
    payload["equipe"]["chef_projet_invite"] = {
        "nom": "Invité",
        "prenom": "Test",
        "email": "rollback.contexte@demo.ci",
    }
    with schema_context("demo"):
        serializer = ProjetCreationSerializer(data=payload)
        assert serializer.is_valid(), serializer.errors
        with (
            patch(
                "apps.projets.serializers.Projet.objects.create",
                side_effect=RuntimeError("échec"),
            ),
            pytest.raises(RuntimeError),
        ):
            serializer.save()
        assert not Utilisateur.objects.filter(email="rollback.contexte@demo.ci").exists()
        assert not Projet.objects.filter(nom=payload["nom"]).exists()


def test_jwt_signature_invalide_refuse(membres, payload):
    import jwt

    token = jwt.encode(
        {"user_id": str(membres["admin"].pk), "schema": "demo", "token_type": "access"},
        "cle-invalide-pour-le-test-uniquement",
        algorithm="HS256",
    )
    client = APIClient(HTTP_HOST="localhost")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert client.get(URL).status_code == 401
    assert client.post("/api/v1/projets/", payload, format="json").status_code == 401


def test_isolation_entre_deux_entreprises(membres, payload):
    with schema_context("public"):
        autre = Entreprise(
            schema_name="contexte_autre",
            raison_sociale="Autre entreprise",
            email_contact="autre@contexte.ci",
            statut=StatutEntreprise.ACTIF,
        )
        autre.save(verbosity=0)
    with schema_context(autre.schema_name):
        externe = Utilisateur.objects.create_user(email="externe@contexte.ci", nom="Externe")
        tiers_externe = Tiers.objects.create(
            raison_sociale="Client externe",
            telephone="0102030405",
        )
    client = client_jwt(membres["admin"])
    contexte = client.get(URL, HTTP_X_TENANT=autre.schema_name).json()
    assert contexte["entreprise"]["schema_name"] == "demo"
    assert str(externe.pk) not in {u["id"] for u in contexte["collaborateurs"]}
    assert str(tiers_externe.pk) not in {t["id"] for t in contexte["clients"]}
    payload["equipe"]["chefs_chantier_ids"] = [str(externe.pk)]
    assert (
        creer_projet_via_service(client, "/api/v1/projets/", payload, format="json").status_code
        == 400
    )
    payload["equipe"]["chefs_chantier_ids"] = [str(membres["cc"].pk)]
    payload["client"] = str(tiers_externe.pk)
    assert (
        creer_projet_via_service(client, "/api/v1/projets/", payload, format="json").status_code
        == 400
    )
    payload["client"] = str(membres["client"].pk)
    formulaire = {
        "nom": "Isolation formulaire",
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Man",
        "maitre_ouvrage": "Client",
    }
    response = client.post(
        "/api/v1/projets/",
        formulaire,
        format="json",
        HTTP_X_TENANT=autre.schema_name,
    )
    assert response.status_code == 201
    with schema_context(autre.schema_name):
        assert not Projet.objects.filter(reference=response.data["reference"]).exists()
    with schema_context("demo"):
        assert (
            Projet.objects.get(reference=response.data["reference"]).cree_par_id
            == membres["admin"].pk
        )
