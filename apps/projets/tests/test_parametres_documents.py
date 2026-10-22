"""Tests du réglage de l'en-tête et du pied des documents PDF — `/api/v1/entreprise/documents/`."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.audit.models import JournalAudit
from apps.core.droits import DROITS_ADMIN_AD, a_permission
from apps.core.enums import ActionAudit, RoleGlobal
from apps.core.registre_permissions import REGISTRE
from apps.projets.models import ParametresDocuments
from apps.tenants.models import Entreprise, TelephoneEntreprise

HOTE = "demo.localhost"
URL = "/api/v1/entreprise/documents/"


@pytest.fixture
def utilisateurs(schema_demo):
    initialiser_roles_par_defaut()

    def creer(code, email):
        return Utilisateur.objects.create_user(
            email=email,
            role_global=code,
            role=Role.objects.filter(code=code).first(),
            nom=code,
            prenom="Test",
        )

    return {
        "dg": creer(RoleGlobal.DIRECTEUR_GENERAL, "dg_docs@demo.ci"),
        "ad": creer(RoleGlobal.ADMIN, "ad_docs@demo.ci"),
        "cc": creer(RoleGlobal.CHEF_CHANTIER, "cc_docs@demo.ci"),
    }


@pytest.fixture
def entreprise():
    tenant = Entreprise.objects.get(schema_name="demo")
    tenant.raison_sociale = "SOUMAFE SARL"
    tenant.nom_commercial = ""
    tenant.rccm = "CI-ABJ-2020-B-12345"
    tenant.nif = "1234567A"
    tenant.adresse = "Cocody, Abidjan"
    tenant.ville = ""
    tenant.logo = ""
    tenant.logo_original = ""
    tenant.telephone_contact = ""
    tenant.save()
    return tenant


def _client(utilisateur):
    client = APIClient()
    client.force_authenticate(user=utilisateur)
    return client


@pytest.mark.django_db
def test_lecture_par_un_chef_de_chantier(utilisateurs, entreprise):
    rep = _client(utilisateurs["cc"]).get(URL, HTTP_HOST=HOTE)

    assert rep.status_code == status.HTTP_200_OK
    corps = rep.json()
    assert corps["reglage"] == {
        "entete_afficher_logo": True,
        "entete_mentions": ["raison_sociale", "rccm", "nif"],
        "entete_texte_libre": "",
        "pied_mentions": ["raison_sociale", "adresse", "telephone"],
        "pied_texte_libre": "",
    }
    assert corps["entete"]["logo_url"] is None


@pytest.mark.django_db
def test_une_seule_ligne_par_entreprise(utilisateurs, entreprise):
    client = _client(utilisateurs["cc"])
    client.get(URL, HTTP_HOST=HOTE)
    client.get(URL, HTTP_HOST=HOTE)

    assert ParametresDocuments.objects.count() == 1
    assert ParametresDocuments.courant().pk == ParametresDocuments.courant().pk


@pytest.mark.django_db
def test_lignes_resolues_avec_rccm_et_nif(utilisateurs, entreprise):
    rep = _client(utilisateurs["cc"]).get(URL, HTTP_HOST=HOTE)

    assert rep.json()["entete"]["lignes"] == [
        "SOUMAFE SARL",
        "RCCM : CI-ABJ-2020-B-12345",
        "NIF : 1234567A",
    ]


@pytest.mark.django_db
def test_mention_vide_omise(utilisateurs, entreprise):
    entreprise.nif = ""
    entreprise.save()

    rep = _client(utilisateurs["cc"]).get(URL, HTTP_HOST=HOTE)

    lignes = rep.json()["entete"]["lignes"]
    assert lignes == ["SOUMAFE SARL", "RCCM : CI-ABJ-2020-B-12345"]
    assert not any(ligne.startswith("NIF") for ligne in lignes)


@pytest.mark.django_db
def test_pied_avec_telephone_principal_et_texte_libre(utilisateurs, entreprise):
    TelephoneEntreprise.objects.create(
        entreprise=entreprise,
        libelle=TelephoneEntreprise.Libelle.MOBILE,
        numero="+2250700000001",
        est_principal=False,
        ordre=1,
    )
    TelephoneEntreprise.objects.create(
        entreprise=entreprise,
        libelle=TelephoneEntreprise.Libelle.STANDARD,
        numero="+2250700000002",
        est_principal=True,
    )
    parametres = ParametresDocuments.courant()
    parametres.pied_texte_libre = "SARL au capital de 10 000 000 FCFA"
    parametres.save()

    rep = _client(utilisateurs["cc"]).get(URL, HTTP_HOST=HOTE)

    assert rep.json()["pied"]["lignes"] == [
        "SOUMAFE SARL",
        "Cocody, Abidjan",
        "Tél : +2250700000002",
        "SARL au capital de 10 000 000 FCFA",
    ]


@pytest.mark.django_db
def test_logo_masque_quand_non_affiche(utilisateurs, entreprise):
    entreprise.logo_original = "demo/logos/logo_original.png"
    entreprise.save()
    client = _client(utilisateurs["dg"])

    rep = client.get(URL, HTTP_HOST=HOTE)
    assert rep.json()["entete"]["logo_url"].endswith("demo/logos/logo_original.png")

    rep = client.patch(URL, {"entete_afficher_logo": False}, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["entete"]["logo_url"] is None


@pytest.mark.django_db
def test_modification_refusee_au_chef_de_chantier(utilisateurs, entreprise):
    rep = _client(utilisateurs["cc"]).patch(
        URL, {"pied_texte_libre": "Pirate"}, format="json", HTTP_HOST=HOTE
    )

    assert rep.status_code == status.HTTP_403_FORBIDDEN
    assert rep.json()["erreur"]["code"] == "acces_refuse"
    assert ParametresDocuments.courant().pied_texte_libre == ""


@pytest.mark.django_db
def test_modification_acceptee_au_dg_et_a_l_ad(utilisateurs, entreprise):
    rep = _client(utilisateurs["dg"]).patch(
        URL,
        {
            "entete_mentions": ["nif", "raison_sociale"],
            "entete_texte_libre": "Bâtiment et travaux publics",
            "pied_texte_libre": "SARL au capital de 10 000 000 FCFA",
        },
        format="json",
        HTTP_HOST=HOTE,
    )

    assert rep.status_code == status.HTTP_200_OK
    corps = rep.json()
    assert corps["reglage"]["entete_mentions"] == ["nif", "raison_sociale"]
    assert corps["entete"]["lignes"] == [
        "NIF : 1234567A",
        "SOUMAFE SARL",
        "Bâtiment et travaux publics",
    ]
    assert corps["pied"]["lignes"][-1] == "SARL au capital de 10 000 000 FCFA"

    rep_ad = _client(utilisateurs["ad"]).patch(
        URL, {"pied_texte_libre": ""}, format="json", HTTP_HOST=HOTE
    )
    assert rep_ad.status_code == status.HTTP_200_OK
    assert ParametresDocuments.courant().pied_texte_libre == ""


@pytest.mark.django_db
def test_code_inconnu_refuse_400(utilisateurs, entreprise):
    rep = _client(utilisateurs["dg"]).patch(
        URL, {"entete_mentions": ["raison_sociale", "capital"]}, format="json", HTTP_HOST=HOTE
    )

    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert "entete_mentions" in rep.json()["erreur"]["details"]
    assert ParametresDocuments.courant().entete_mentions == ["raison_sociale", "rccm", "nif"]


@pytest.mark.django_db
def test_code_repete_refuse_400(utilisateurs, entreprise):
    rep = _client(utilisateurs["dg"]).patch(
        URL, {"pied_mentions": ["rccm", "rccm"]}, format="json", HTTP_HOST=HOTE
    )

    assert rep.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_texte_libre_trop_long_refuse_400(utilisateurs, entreprise):
    rep = _client(utilisateurs["dg"]).patch(
        URL, {"entete_texte_libre": "x" * 201}, format="json", HTTP_HOST=HOTE
    )

    assert rep.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_modification_journalisee_avant_apres(utilisateurs, entreprise):
    rep = _client(utilisateurs["dg"]).patch(
        URL, {"pied_texte_libre": "Capital 1 000 000 FCFA"}, format="json", HTTP_HOST=HOTE
    )
    assert rep.status_code == status.HTTP_200_OK

    entree = JournalAudit.objects.get(type_entite="parametres_documents")
    assert entree.action == ActionAudit.MODIFICATION
    assert entree.utilisateur_id == utilisateurs["dg"].pk
    assert entree.valeur_avant["pied_texte_libre"] == ""
    assert entree.valeur_apres["pied_texte_libre"] == "Capital 1 000 000 FCFA"


@pytest.mark.django_db
def test_permission_au_registre_et_pour_l_ad(utilisateurs):
    perm = REGISTRE["administration.documents_gerer"]
    assert perm.module == "administration"
    assert perm.reservee_administration is True
    assert perm.libelle == "Configurer l'en-tête et le pied des documents"
    assert "administration.documents_gerer" in DROITS_ADMIN_AD

    assert a_permission(utilisateurs["dg"], "administration.documents_gerer") is True
    assert a_permission(utilisateurs["ad"], "administration.documents_gerer") is True
    assert a_permission(utilisateurs["cc"], "administration.documents_gerer") is False
