"""Suppression définitive d'une entreprise cliente (phase de test du MVP)."""

import pytest
from django.db import connection
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import Entreprise, RegistreEmail

HOTE = "localhost"
# `tenant_b` est créé une fois par session (conftest.py). DROP SCHEMA est transactionnel : le retour
# arrière de pytest le restaure après le test, ce qui évite de rejouer les migrations ici.
SCHEMA = "tenant_b"
EMAIL_A = "dirigeant.sup.a@example.com"


@pytest.fixture
def client_api():
    return APIClient(headers={"host": HOTE})


def _agent(email, superuser):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = Utilisateur.objects.create_superuser if superuser else Utilisateur.objects.create_user
        return fabrique(
            email=email, password="MotDePasse12345!", nom="Agent", prenom="Plateforme",
            role_global=RoleGlobal.ADMIN, statut=StatutUtilisateur.ACTIF,
            **({} if superuser else {"is_staff": True}),
        )


def _entreprise_de_test():
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(schema_name=SCHEMA)
        RegistreEmail.objects.get_or_create(email=EMAIL_A, defaults={"entreprise": ent})
        # Un compte de même adresse dans le schéma public (ancien chemin d'inscription) :
        # il doit partir lui aussi, sinon l'adresse reste prise.
        Utilisateur.objects.create_user(
            email=EMAIL_A, password="MotDePasse12345!", nom="Reste", prenom="Public",
            role_global=RoleGlobal.DIRECTEUR_GENERAL, statut=StatutUtilisateur.ACTIF,
        )
    with schema_context(SCHEMA):
        u = Utilisateur.objects.create_user(
            email=EMAIL_A, password="MotDePasse12345!", nom="Dirigeant", prenom="A",
            role_global=RoleGlobal.DIRECTEUR_GENERAL, statut=StatutUtilisateur.ACTIF,
        )
        u.is_owner = True
        u.save(update_fields=["is_owner", "modifie_le"])
    return ent


def _schema_existe(nom):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s;", [nom])
        return cursor.fetchone() is not None


@pytest.mark.django_db
def test_refus_demo_support_et_interrupteur(client_api, settings):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    with schema_context(get_public_schema_name()):
        demo = Entreprise.objects.get(schema_name="demo")
    url = f"/api/v1/admins/clients/{demo.id}/supprimer-definitivement/"

    client_api.force_authenticate(user=_agent("sup.refus.a@ccd-digital.ci", superuser=False))
    assert client_api.post(url, {"confirmation": "demo"}, format="json").status_code == 403  # SUPPORT

    client_api.force_authenticate(user=_agent("sup.refus.b@ccd-digital.ci", superuser=True))
    reponse = client_api.post(url, {"confirmation": "demo"}, format="json")
    assert reponse.status_code == 403 and reponse.json()["erreur"]["code"] == "entreprise_protegee"
    assert _schema_existe("demo")

    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = False
    apercu = client_api.get(f"/api/v1/admins/clients/{demo.id}/suppression/apercu/").json()
    assert apercu["protegee"] is True and apercu["suppression_activee"] is False


@pytest.mark.django_db
def test_suppression_complete_avec_temoin_et_adresse_liberee(client_api, settings):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(user=_agent("sup.suppr@ccd-digital.ci", superuser=True))
    ent = _entreprise_de_test()
    with schema_context(get_public_schema_name()):
        demo = Entreprise.objects.get(schema_name="demo")
        registre_demo_avant = RegistreEmail.objects.filter(entreprise=demo).count()
    with schema_context("demo"):
        utilisateurs_demo_avant = Utilisateur.objects.count()

    apercu = client_api.get(f"/api/v1/admins/clients/{ent.id}/suppression/apercu/").json()
    assert EMAIL_A in apercu["adresses"]
    assert any(d["email"] == EMAIL_A for d in apercu["dirigeants"])

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    mauvais = client_api.post(url, {"confirmation": "autre"}, format="json")
    assert mauvais.status_code == 400 and _schema_existe(SCHEMA)

    reponse = client_api.post(url, {"confirmation": SCHEMA}, format="json")
    assert reponse.status_code == 200, reponse.content

    # L'entreprise a disparu, partout.
    assert not _schema_existe(SCHEMA)
    with schema_context(get_public_schema_name()):
        assert not Entreprise.objects.filter(schema_name=SCHEMA).exists()
        assert not Entreprise.objects.filter(domains__domain="tenant-b.localhost").exists()
        assert not RegistreEmail.objects.filter(email__iexact=EMAIL_A).exists()
        assert not Utilisateur.tous_objets.filter(email__iexact=EMAIL_A).exists()
        assert JournalPlateforme.objects.filter(action="SUPPRESSION_DEFINITIVE_ENTREPRISE").exists()

        # Le témoin est intact.
        assert Entreprise.objects.filter(schema_name="demo").exists()
        assert RegistreEmail.objects.filter(entreprise=demo).count() == registre_demo_avant
    with schema_context("demo"):
        assert Utilisateur.objects.count() == utilisateurs_demo_avant

    # L'adresse est libre : une autre entreprise peut la reprendre, sans heurter l'unicité globale.
    with schema_context(get_public_schema_name()):
        RegistreEmail.objects.create(email=EMAIL_A, entreprise=demo)
        assert RegistreEmail.objects.filter(email__iexact=EMAIL_A).count() == 1
