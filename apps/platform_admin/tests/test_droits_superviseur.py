"""Tests pour la séparation des droits SUPERVISEUR / SUPPORT (B1)."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Plan
from apps.catalogue.models import CatalogueModule
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import Entreprise

SCHEMA_CLIENT = "demo"
HOTE_PLATEFORME = "localhost"


@pytest.fixture(autouse=True)
def autoriser_ip_locale(settings):
    """Autorise l'adresse IP de test dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]


@pytest.fixture
def client_api():
    """Client API configuré sur le domaine de la plateforme."""
    return APIClient(headers={"host": HOTE_PLATEFORME})


def _agent(email: str, superviseur: bool) -> Utilisateur:
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = (
            Utilisateur.objects.create_superuser if superviseur else Utilisateur.objects.create_user
        )
        return fabrique(
            email=email,
            password="MotDePasse12345!",
            nom="Agent",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            **({} if superviseur else {"is_staff": True}),
        )


@pytest.fixture
def agent_support(db):
    return _agent("support.test@ccd-digital.ci", superviseur=False)


@pytest.fixture
def agent_superviseur(db):
    return _agent("superviseur.test@ccd-digital.ci", superviseur=True)


@pytest.fixture
def entreprise_test(db):
    """Prépare l'entreprise cliente demo avec les plans BTP et un abonnement actif."""
    with schema_context(get_public_schema_name()):
        p1, _ = Plan.objects.get_or_create(
            code=Plan.Code.BATISSEUR,
            defaults={
                "libelle": "Bâtisseur",
                "prix_mensuel_montant": 19_000_00,
                "limite_projets": 3,
                "limite_utilisateurs": 5,
            },
        )
        ent = Entreprise.objects.get(schema_name=SCHEMA_CLIENT)
        ent.statut = StatutEntreprise.ACTIF
        ent.save()

        ent.abonnements.all().delete()
        aujourdhui = timezone.now().date()
        Abonnement.objects.create(
            entreprise=ent,
            plan=p1,
            date_debut=aujourdhui - timedelta(days=30),
            date_fin=aujourdhui + timedelta(days=335),
            statut=Abonnement.Statut.ACTIF,
            renouvellement_auto=True,
        )
    return ent


dummy_id = str(uuid.uuid4())

ACTIONS_RESERVEES = [
    ("post", f"/api/v1/admins/clients/{dummy_id}/suspendre/", {"motif": "Suspension test"}),
    ("post", f"/api/v1/admins/clients/{dummy_id}/reactiver/", {}),
    ("patch", f"/api/v1/admins/clients/{dummy_id}/abonnement/", {"plan_code": "BATISSEUR"}),
    (
        "post",
        "/api/v1/admins/comptes/",
        {"email": "agent.cree@ccd.ci", "nom": "N", "prenom": "P", "role": "SUPPORT"},
    ),
    ("post", f"/api/v1/admins/comptes/{dummy_id}/suspendre/", {}),
    ("post", f"/api/v1/admins/comptes/{dummy_id}/reactiver/", {}),
    ("post", "/api/v1/admins/modules/", {"code": "MOD_TEST", "libelle": "Module Test"}),
    ("patch", f"/api/v1/admins/modules/{dummy_id}/", {"libelle": "Modif Libelle"}),
    ("delete", f"/api/v1/admins/modules/{dummy_id}/", {}),
    ("put", f"/api/v1/admins/modules/{dummy_id}/permissions/", {"permissions": []}),
    ("post", f"/api/v1/admins/modules/{dummy_id}/desactiver/", {}),
    ("post", f"/api/v1/admins/modules/{dummy_id}/reactiver/", {}),
    ("post", "/api/v1/admins/permissions/", {"code": "PERM_TEST", "libelle": "Perm Test"}),
    ("patch", f"/api/v1/admins/permissions/{dummy_id}/", {"libelle": "Modif Libelle"}),
    ("delete", f"/api/v1/admins/permissions/{dummy_id}/", {}),
    ("post", f"/api/v1/admins/permissions/{dummy_id}/modules/", {"modules": []}),
]


@pytest.mark.django_db
@pytest.mark.parametrize("methode,url,corps", ACTIONS_RESERVEES)
def test_support_ne_peut_pas_ecrire_sur_les_actions_reservees(
    client_api, agent_support, methode, url, corps
):
    """Le SUPPORT reçoit 403 avec message superviseur et aucune journalisation."""
    with schema_context(get_public_schema_name()):
        nb_journal_avant = JournalPlateforme.objects.count()

    client_api.force_authenticate(user=agent_support)
    methode_client = getattr(client_api, methode)
    reponse = methode_client(url, corps, format="json", HTTP_HOST=HOTE_PLATEFORME)

    assert reponse.status_code == status.HTTP_403_FORBIDDEN
    msg = reponse.json()["erreur"]["message"].lower()
    assert "superviseur" in msg

    with schema_context(get_public_schema_name()):
        nb_journal_apres = JournalPlateforme.objects.count()
    assert nb_journal_avant == nb_journal_apres


@pytest.mark.django_db
def test_support_lit_le_back_office(client_api, agent_support, entreprise_test):
    """Le SUPPORT obtient 200 sur toutes les routes de consultation back-office."""
    client_api.force_authenticate(user=agent_support)
    urls = [
        "/api/v1/admins/clients/",
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        "/api/v1/admins/comptes/",
        "/api/v1/admins/modules/",
        "/api/v1/admins/permissions/",
        "/api/v1/admins/journal-plateforme/",
        "/api/v1/admins/parametres/messagerie/",
    ]
    for url in urls:
        rep = client_api.get(url, HTTP_HOST=HOTE_PLATEFORME)
        assert rep.status_code == status.HTTP_200_OK, f"Échec sur {url}: {rep.content}"


@pytest.mark.django_db
def test_support_active_et_desactive_un_module_client(client_api, agent_support, entreprise_test):
    """Le SUPPORT obtient 200 sur POST desactiver puis activer pour un module hors projets."""
    with schema_context(get_public_schema_name()):
        module = (
            CatalogueModule.objects.exclude(code__iexact="projets")
            .filter(est_actif=True)
            .first()
        )
    if not module:
        pytest.skip("Aucun module actif autre que projets")

    client_api.force_authenticate(user=agent_support)

    url_desact = f"/api/v1/admins/clients/{entreprise_test.id}/modules/{module.id}/desactiver/"
    rep_desact = client_api.post(url_desact, HTTP_HOST=HOTE_PLATEFORME)
    assert rep_desact.status_code == status.HTTP_200_OK

    url_act = f"/api/v1/admins/clients/{entreprise_test.id}/modules/{module.id}/activer/"
    rep_act = client_api.post(url_act, HTTP_HOST=HOTE_PLATEFORME)
    assert rep_act.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_superviseur_suspend_toujours(client_api, agent_superviseur, entreprise_test):
    """Le superviseur suspend l'entreprise de test : 200, statut SUSPENDU."""
    client_api.force_authenticate(user=agent_superviseur)
    url = f"/api/v1/admins/clients/{entreprise_test.id}/suspendre/"
    rep = client_api.post(
        url,
        {"motif": "Non-paiement après plusieurs relances formelles."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["statut"] == "SUSPENDU"


@pytest.mark.django_db
def test_support_ne_cree_pas_de_compte_superviseur(client_api, agent_support):
    """POST /api/v1/admins/comptes/ avec role SUPERVISEUR par SUPPORT : 403 et non créé."""
    email_cible = "nouveau.superviseur@ccd.ci"
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email_cible).delete()

    client_api.force_authenticate(user=agent_support)
    rep = client_api.post(
        "/api/v1/admins/comptes/",
        {
            "email": email_cible,
            "nom": "Super",
            "prenom": "Viseur",
            "role": "SUPERVISEUR",
        },
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    assert "superviseur" in rep.json()["erreur"]["message"].lower()

    with schema_context(get_public_schema_name()):
        assert not Utilisateur.tous_objets.filter(email=email_cible).exists()


@pytest.mark.django_db
def test_profil_expose_le_role_support(client_api, agent_support):
    """GET /api/v1/admins/moi/ par SUPPORT : role == 'SUPPORT' et is_superuser is False."""
    client_api.force_authenticate(user=agent_support)
    rep = client_api.get("/api/v1/admins/moi/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_200_OK
    donnees = rep.json()
    assert donnees["role"] == "SUPPORT"
    assert donnees["is_superuser"] is False
