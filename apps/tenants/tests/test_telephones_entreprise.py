"""Tests complets pour la gestion des numéros de contact par entreprise — B3 (MLD §4.1.1)."""

import importlib
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import get_public_schema_name, schema_context
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.tenants.models import Entreprise, TelephoneEntreprise
from apps.tenants.services.telephones import est_e164, normaliser_telephone

migration_0013 = importlib.import_module(
    "apps.tenants.migrations.0013_reprendre_telephone_contact"
)
reprendre_telephone_contact = migration_0013.reprendre_telephone_contact

HOTE = "demo.localhost"
SCHEMA = "demo"
HOTE_ADMIN = "localhost"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def client_admin(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    return APIClient(headers={"host": HOTE_ADMIN})


@pytest.fixture
def super_admin(db):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="admin.b3@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="admin.b3@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Super",
            prenom="Admin",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_staff=True,
            is_superuser=True,
        )


@pytest.fixture
def utilisateur_dg(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="dg.telephones@ccd-digital.ci",
            defaults={
                "is_active": True,
                "role_global": RoleGlobal.DIRECTEUR_GENERAL,
            },
        )
        user.role_global = RoleGlobal.DIRECTEUR_GENERAL
        user.set_password("MotDePasse1!")
        user.save()
        return user


@pytest.fixture
def utilisateur_sans_droit(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email="chef.chantier@ccd-digital.ci",
            defaults={
                "is_active": True,
                "role_global": RoleGlobal.CHEF_CHANTIER,
            },
        )
        user.role_global = RoleGlobal.CHEF_CHANTIER
        user.set_password("MotDePasse1!")
        user.save()
        return user


def _creer_image_test():
    fichier = io.BytesIO()
    image = Image.new("RGB", (30, 30), color=(30, 96, 145))
    image.save(fichier, format="PNG")
    fichier.seek(0)
    return SimpleUploadedFile("logo_test.png", fichier.read(), content_type="image/png")


def test_normaliser_telephone():
    """Vérifie le nettoyage des caractères et le préfixe 00."""
    assert normaliser_telephone("+225 07 00-00.00 00") == "+2250700000000"
    assert normaliser_telephone("002250700000000") == "+2250700000000"
    assert normaliser_telephone("+33 (0)6.12-34/56 78") == "+330612345678"
    assert normaliser_telephone("") == ""
    assert normaliser_telephone(None) == ""


def test_e164_tous_pays():
    """Vérifie la conformité E.164 internationale."""
    # Valides
    assert est_e164("+2250700000000") is True
    assert est_e164("+33612345678") is True
    assert est_e164("+14155552671") is True
    assert est_e164("+8613800138000") is True

    # Invalides
    assert est_e164("0700000000") is False
    assert est_e164("+02250700000000") is False
    assert est_e164("+22") is False
    assert est_e164("+1234567890123456") is False  # 16 chiffres après +


@pytest.mark.django_db
def test_enregistrer_trois_numeros(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "numero": "+2250700000000", "principal": True},
            {"libelle": "FIXE", "numero": "+2252700000000", "principal": False},
            {"libelle": "WHATSAPP", "numero": "+33612345678", "principal": False},
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_200_OK
    assert len(reponse.data["telephones"]) == 3
    assert reponse.data["telephones"][0]["principal"] is True
    assert reponse.data["telephones"][0]["numero"] == "+2250700000000"
    assert reponse.data["telephone_contact"] == "+2250700000000"

    # Vérification lecture GET
    rep_get = client.get("/api/v1/parametres/configuration/")
    assert rep_get.status_code == status.HTTP_200_OK
    assert len(rep_get.data["telephones"]) == 3
    assert rep_get.data["telephones"][0]["libelle_affiche"] == "Mobile"


@pytest.mark.django_db
def test_nom_libre_enregistre_modifie_et_journalise(client, utilisateur_dg):
    """MLD v1.8 : le nom est facultatif, nettoyé, relu, et sa modification journalisée."""
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {
                "libelle": "WHATSAPP",
                "nom": "  Service achats ",
                "numero": "+2250700000000",
                "principal": True,
            },
            {"libelle": "FIXE", "numero": "+2252700000000", "principal": False},
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["telephones"][0]["nom"] == "Service achats"
    assert reponse.data["telephones"][1]["nom"] == ""

    payload["telephones"][0]["id"] = reponse.data["telephones"][0]["id"]
    payload["telephones"][0]["nom"] = "Direction"
    with schema_context(SCHEMA):
        avant = JournalAudit.objects.filter(type_entite="telephone_entreprise").count()
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_200_OK
    assert client.get("/api/v1/parametres/configuration/").data["telephones"][0]["nom"] == (
        "Direction"
    )
    with schema_context(SCHEMA):
        assert JournalAudit.objects.filter(type_entite="telephone_entreprise").count() == (
            avant + 1
        )


@pytest.mark.django_db
def test_nom_trop_long_refuse(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "nom": "x" * 61, "numero": "+2250700000000", "principal": True}
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_multipart_avec_logo_et_numeros(client, utilisateur_dg, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_authenticate(user=utilisateur_dg)
    telephones_json = json.dumps(
        [
            {"libelle": "STANDARD", "numero": "+2252722000000", "principal": True},
            {"libelle": "COMPTABILITE", "numero": "+2250701020304", "principal": False},
        ]
    )
    image = _creer_image_test()
    reponse = client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": telephones_json,
            "fichier_logo": image,
        },
        format="multipart",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert len(reponse.data["telephones"]) == 2
    assert reponse.data["telephone_contact"] == "+2252722000000"


@pytest.mark.django_db
def test_changer_de_principal(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250700000001", "principal": True},
                {"libelle": "FIXE", "numero": "+2252700000001", "principal": False},
            ]
        },
        format="json",
    )

    reponse = client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250700000001", "principal": False},
                {"libelle": "FIXE", "numero": "+2252700000001", "principal": True},
            ]
        },
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["telephone_contact"] == "+2252700000001"
    assert reponse.data["telephones"][0]["numero"] == "+2252700000001"
    assert reponse.data["telephones"][0]["principal"] is True


@pytest.mark.django_db
def test_retrait_logique(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    rep1 = client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250700000010", "principal": True},
                {"libelle": "FIXE", "numero": "+2252700000010", "principal": False},
            ]
        },
        format="json",
    )
    id_fixe = rep1.data["telephones"][1]["id"]

    # On ne conserve que le mobile
    rep2 = client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250700000100", "principal": True},
            ]
        },
        format="json",
    )
    assert rep2.status_code == status.HTTP_200_OK
    assert len(rep2.data["telephones"]) == 1

    with schema_context(get_public_schema_name()):
        tel_supprime = TelephoneEntreprise.tous_objets.get(id=id_fixe)
        assert tel_supprime.supprime_le is not None


@pytest.mark.django_db
def test_six_numeros_refuses(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "numero": f"+225070000000{i}", "principal": (i == 0)}
            for i in range(6)
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    contenu = reponse.json()
    assert "Cinq numéros au plus" in str(contenu)


@pytest.mark.django_db
def test_sans_principal_refuse(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "numero": "+2250700000000", "principal": False},
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    assert "Désignez un, et un seul" in str(reponse.json())


@pytest.mark.django_db
def test_deux_principaux_refuses(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "numero": "+2250700000000", "principal": True},
            {"libelle": "FIXE", "numero": "+2252700000000", "principal": True},
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    assert "Désignez un, et un seul" in str(reponse.json())


@pytest.mark.django_db
def test_doublon_refuse(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "numero": "+2250700000000", "principal": True},
            {"libelle": "WHATSAPP", "numero": "+225 07 00 00 00 00", "principal": False},
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    assert "figure deux fois" in str(reponse.json())


@pytest.mark.django_db
def test_numero_invalide_sous_sa_ligne(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    payload = {
        "telephones": [
            {"libelle": "MOBILE", "numero": "+2250700000000", "principal": True},
            {"libelle": "FIXE", "numero": "0700000000", "principal": False},
        ]
    }
    reponse = client.patch("/api/v1/parametres/configuration/", payload, format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    data = reponse.json()
    details = data.get("erreur", {}).get("details", data)
    assert "telephones" in details
    assert "1" in details["telephones"]
    assert "numero" in details["telephones"]["1"]


@pytest.mark.django_db
def test_ancien_client_telephone_contact_seul(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    # Préparation : créer un mobile secondaire et un principal
    client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250700000000", "principal": True},
                {"libelle": "WHATSAPP", "numero": "+2250500000000", "principal": False},
            ]
        },
        format="json",
    )

    # Ancien client envoyant seulement telephone_contact
    reponse = client.patch(
        "/api/v1/parametres/configuration/",
        {"telephone_contact": "+225 01 02 03 04 05"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["telephone_contact"] == "+2250102030405"
    assert len(reponse.data["telephones"]) == 2
    # Le principal est mis à jour, le WhatsApp reste
    assert reponse.data["telephones"][0]["numero"] == "+2250102030405"
    assert reponse.data["telephones"][1]["numero"] == "+2250500000000"


@pytest.mark.django_db
def test_telephone_contact_invalide_refuse(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    reponse = client.patch(
        "/api/v1/parametres/configuration/",
        {"telephone_contact": "12"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_sans_permission_refuse(client, utilisateur_sans_droit):
    client.force_authenticate(user=utilisateur_sans_droit)
    reponse = client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250700000000", "principal": True},
            ]
        },
        format="json",
    )
    assert reponse.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_journal_audit(client, utilisateur_dg):
    client.force_authenticate(user=utilisateur_dg)
    with schema_context(SCHEMA):
        nb_avant = JournalAudit.objects.filter(type_entite="telephone_entreprise").count()

    client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250799887766", "principal": True},
            ]
        },
        format="json",
    )

    with schema_context(SCHEMA):
        nb_apres = JournalAudit.objects.filter(type_entite="telephone_entreprise").count()
        assert nb_apres == nb_avant + 1

    # Un PATCH identique ne doit pas créer de nouvelle entrée
    client.patch(
        "/api/v1/parametres/configuration/",
        {
            "telephones": [
                {"libelle": "MOBILE", "numero": "+2250799887766", "principal": True},
            ]
        },
        format="json",
    )

    with schema_context(SCHEMA):
        nb_identique = JournalAudit.objects.filter(type_entite="telephone_entreprise").count()
        assert nb_identique == nb_apres


@pytest.mark.django_db
def test_journal_audit_modification_d_un_numero_existant(client, utilisateur_dg):
    """Changer le libellé d'un numéro déjà enregistré se journalise, avec le vrai « avant »."""
    client.force_authenticate(user=utilisateur_dg)
    url = "/api/v1/parametres/configuration/"
    rep = client.patch(
        url,
        {"telephones": [{"libelle": "MOBILE", "numero": "+2250799887766", "principal": True}]},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content
    identifiant = rep.json()["telephones"][0]["id"]
    with schema_context(SCHEMA):
        nb_avant = JournalAudit.objects.filter(type_entite="telephone_entreprise").count()

    rep = client.patch(
        url,
        {
            "telephones": [
                {
                    "id": identifiant,
                    "libelle": "WHATSAPP",
                    "numero": "+2250799887766",
                    "principal": True,
                }
            ]
        },
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content

    with schema_context(SCHEMA):
        entrees = JournalAudit.objects.filter(type_entite="telephone_entreprise")
        assert entrees.count() == nb_avant + 1
        derniere = entrees.order_by("-id").first()
        assert derniere.valeur_avant[0]["libelle"] == "MOBILE"
        assert derniere.valeur_apres[0]["libelle"] == "WHATSAPP"


@pytest.mark.django_db
def test_fiche_back_office_expose_les_numeros(client_admin, super_admin):
    client_admin.force_authenticate(user=super_admin)
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(schema_name=SCHEMA)
        TelephoneEntreprise.objects.create(
            entreprise=ent,
            libelle="STANDARD",
            numero="+2252720000000",
            est_principal=True,
            ordre=0,
        )

    reponse = client_admin.get(f"/api/v1/admins/clients/{ent.id}/")
    assert reponse.status_code == status.HTTP_200_OK
    assert "telephones" in reponse.data
    assert len(reponse.data["telephones"]) >= 1
    assert reponse.data["telephones"][0]["numero"] == "+2252720000000"


@pytest.mark.django_db
def test_migration_reprend_l_ancien_numero(db):
    """Vérifie l'exécution directe de la fonction de migration 0013."""
    from django.apps import apps

    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(schema_name=SCHEMA)
        ent.telephone_contact = "+225 07 00 00 00 00"
        ent.save(update_fields=["telephone_contact"])
        TelephoneEntreprise.objects.filter(entreprise=ent).delete()

        reprendre_telephone_contact(apps, None)

        tel = TelephoneEntreprise.objects.filter(entreprise=ent, est_principal=True).first()
        assert tel is not None
        assert tel.numero == "+2250700000000"
        assert tel.libelle == "STANDARD"
