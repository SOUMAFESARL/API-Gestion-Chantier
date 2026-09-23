"""Validation avant creation d'espace : droits, transitions et audit."""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import DemandeInscription, Entreprise
from apps.tenants.services.inscription import activer, deposer, provisionner

pytestmark = pytest.mark.django_db
BASE = "/api/v1/admins/inscriptions/"


def test_validation_avec_jeton_de_connexion(
    admin_client, demande, django_capture_on_commit_callbacks
):
    client, admin = admin_client
    objet = verifier_email(demande)
    client.force_authenticate(None)
    connexion = client.post(
        "/api/v1/admins/connexion/",
        {
            "email": admin.email,
            "mot_de_passe": "SuperPassword123!",
            "origine": "WEB",
        },
        format="json",
    )
    assert connexion.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {connexion.data['access']}")
    assert client.get(BASE + "?statut=A_VALIDER").status_code == 200
    with patch("apps.tenants.tasks.provisionner_entreprise.delay") as tache:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(f"{BASE}{objet.pk}/approuver/")
        assert response.status_code == 202, response.data
        tache.assert_called_once_with(str(objet.pk))


@pytest.fixture
def admin_client(db):
    with schema_context("public"):
        admin = Utilisateur.objects.create_superuser(
            email="validation@plateforme.ci",
            password="SuperPassword123!",
            nom="Validation",
            prenom="Admin",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(headers={"host": "localhost"})
    connexion = client.post(
        "/api/v1/admins/connexion/",
        {
            "email": admin.email,
            "mot_de_passe": "SuperPassword123!",
            "origine": "WEB",
        },
        format="json",
    )
    assert connexion.status_code == 200, connexion.data
    client.force_authenticate(admin)
    return client, admin


@pytest.fixture
def demande(db):
    jeton = uuid.uuid4()
    demande = DemandeInscription.objects.create(
        raison_sociale="Validation BTP",
        pays="CI",
        email="validation@entreprise.ci",
        slug_reserve="validation_btp",
        empreinte=DemandeInscription.empreinte_de(jeton),
        expire_le=timezone.now() + timedelta(hours=48),
        cgu_version="1",
        cgu_acceptees_le=timezone.now(),
    )
    return demande, str(jeton)


def verifier_email(demande):
    objet, jeton = demande
    activer(jeton, nom="Client", prenom="Test", mot_de_passe="MotDePasse1!")
    objet.refresh_from_db()
    return objet


def test_email_verifie_sans_provisionnement(demande, django_capture_on_commit_callbacks):
    with patch("apps.tenants.tasks.provisionner_entreprise.delay") as tache:
        with django_capture_on_commit_callbacks(execute=True):
            objet = verifier_email(demande)
        assert objet.statut == "A_VALIDER"
        tache.assert_not_called()
        provisionner(objet.pk)
        assert not Entreprise.objects.filter(schema_name=objet.slug_reserve).exists()


def test_approbation_idempotente_et_auditee(
    admin_client, demande, django_capture_on_commit_callbacks
):
    client, admin = admin_client
    objet = verifier_email(demande)
    with patch("apps.tenants.tasks.provisionner_entreprise.delay") as tache:
        with django_capture_on_commit_callbacks(execute=True):
            reponse = client.post(f"{BASE}{objet.pk}/approuver/")
        assert reponse.status_code == 202, reponse.data
        tache.assert_called_once_with(str(objet.pk))
        with django_capture_on_commit_callbacks(execute=True):
            assert client.post(f"{BASE}{objet.pk}/approuver/").status_code == 202
        tache.assert_called_once()
    objet.refresh_from_db()
    assert objet.statut == "PROVISIONNEMENT"
    assert objet.decision_par == admin.pk
    assert objet.decision_le
    assert JournalPlateforme.objects.filter(action="INSCRIPTION_APPROUVEE").count() == 1
    assert client.post(f"{BASE}{objet.pk}/refuser/", {"motif": "Trop tard"}).status_code == 409


def test_refus_motif_suivi_et_nettoyage(admin_client, demande):
    client, _ = admin_client
    objet = verifier_email(demande)
    assert client.post(f"{BASE}{objet.pk}/refuser/", {"motif": "  "}).status_code == 400
    with patch("apps.tenants.tasks.provisionner_entreprise.delay") as tache:
        reponse = client.post(f"{BASE}{objet.pk}/refuser/", {"motif": "Dossier incomplet"})
        assert reponse.status_code == 200
        assert (
            client.post(f"{BASE}{objet.pk}/refuser/", {"motif": "Autre motif"}).status_code == 200
        )
        tache.assert_not_called()
    objet.refresh_from_db()
    assert objet.statut == "REFUSEE"
    assert objet.motif_refus == "Dossier incomplet"
    assert objet.mot_de_passe_transitoire == ""
    assert JournalPlateforme.objects.filter(action="INSCRIPTION_REFUSEE").count() == 1
    public = APIClient(headers={"host": "localhost"})
    suivi = public.get(f"/api/v1/inscription/etat/{objet.pk}/").json()
    assert suivi == {"statut": "REFUSEE", "motif_refus": "Dossier incomplet"}
    assert client.post(f"{BASE}{objet.pk}/approuver/").status_code == 409


def test_non_verifie_inconnu_et_filtrage(admin_client, demande):
    client, _ = admin_client
    objet, _ = demande
    assert client.post(f"{BASE}{objet.pk}/approuver/").status_code == 409
    assert client.post(f"{BASE}{uuid.uuid4()}/approuver/").status_code == 404
    assert client.get(BASE + "?statut=A_VALIDER").json()["total"] == 0
    verifier_email(demande)
    resultat = client.get(BASE + "?statut=A_VALIDER").json()["resultats"]
    assert len(resultat) == 1
    for interdit in ["mot_de_passe_transitoire", "empreinte", "slug_reserve"]:
        assert interdit not in resultat[0]
        assert interdit not in client.get(f"{BASE}{objet.pk}/").json()
    assert client.get(BASE + "?statut=INVALIDE").status_code == 400


def test_admin_entreprise_et_anonyme_refuses(admin_client, demande):
    client, admin = admin_client
    objet = verifier_email(demande)
    client.force_authenticate(None)
    assert client.get(BASE).status_code == 401
    admin.is_superuser = False
    client.force_authenticate(admin)
    assert client.get(BASE).status_code == 403
    assert client.post(f"{BASE}{objet.pk}/approuver/").status_code == 403
    admin.is_superuser = True
    tenant = APIClient(headers={"host": "demo.localhost"})
    tenant.force_authenticate(admin)
    assert tenant.get(BASE).status_code == 403


def test_email_et_slug_reserves_en_validation(demande):
    objet = verifier_email(demande)
    from apps.tenants.services.inscription import InscriptionEnCours

    with pytest.raises(InscriptionEnCours):
        deposer(identifiant=None, raison_sociale="Autre", pays="CI", email=objet.email)
    with pytest.raises(IntegrityError), transaction.atomic():
        DemandeInscription.objects.create(
            raison_sociale="Autre",
            pays="CI",
            email="autre@entreprise.ci",
            slug_reserve=objet.slug_reserve,
            empreinte=uuid.uuid4().hex,
            expire_le=timezone.now(),
            cgu_version="1",
            cgu_acceptees_le=timezone.now(),
        )
