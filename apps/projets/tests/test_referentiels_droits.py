"""Référentiels : doublon explicite, permission d'ajout, suppression réservée, groupe."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.catalogue.models import CataloguePermission
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.core.registre_permissions import REGISTRE

pytestmark = pytest.mark.django_db

SCHEMA = "demo"
URL_TYPES = "/api/v1/referentiels/types-projet/"
URL_LOTS = "/api/v1/referentiels/lots/"
URL_DROITS = "/api/v1/referentiels/droits/"
URL_ADMIN_LOTS = "/api/v1/admins/referentiels/lots/"
PERMISSION = "projets.referentiels_ajouter"


def _client(email, role_global):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.objects.get_or_create(
            email=email, defaults={"is_active": True, "role_global": role_global}
        )
        user.role_global = role_global
        user.save()
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(user=user)
    return client


def _accorder(code_role, code_permission=PERMISSION):
    """Coche la permission dans la matrice du rôle, comme le fait le DG."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role = Role.objects.get(code=code_role, supprime_le__isnull=True)
        rmp = RoleModulePermission.objects.filter(role=role, module__code="projets").first()
        permission = CataloguePermission.objects.get(code=code_permission, supprime_le__isnull=True)
        rmp.permissions_catalogue.add(permission)


@pytest.fixture
def client_dg():
    return _client("dg.referentiels.droits@ccd-digital.ci", RoleGlobal.DIRECTEUR_GENERAL)


@pytest.fixture
def client_cp():
    return _client("cp.referentiels.droits@ccd-digital.ci", RoleGlobal.CHEF_PROJET)


@pytest.fixture
def client_ct():
    return _client("ct.referentiels.droits@ccd-digital.ci", RoleGlobal.CONDUCTEUR_TRAVAUX)


@pytest.fixture
def client_admin_plateforme(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superviseur.droits@ccd-digital.ci").delete()
        admin = Utilisateur.objects.create_superuser(
            email="superviseur.droits@ccd-digital.ci",
            password="MotDePasse12345!",
            nom="Superviseur",
            prenom="Droits",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(HTTP_HOST="localhost")
    client.force_authenticate(admin)
    return client


# --- Registre ---------------------------------------------------------------


def test_permission_au_registre_attribuable():
    definition = REGISTRE[PERMISSION]
    assert definition.module == "projets"
    assert definition.libelle == "Ajouter des types, groupes et listes de l'entreprise"
    assert definition.reservee_administration is False


def test_permission_par_defaut_dg_ad_do_cp():
    from apps.accounts.services.roles import PERMISSIONS_DEFAUT_ROLES

    avec = {
        r for r, modules in PERMISSIONS_DEFAUT_ROLES.items() if PERMISSION in modules["projets"]
    }
    assert avec == {"DG", "AD", "DO", "CP"}


# --- Doublon explicite -------------------------------------------------------


def test_doublon_entreprise_409_nomme_l_entree_existante(client_dg):
    rep = client_dg.post(URL_LOTS, {"libelle": "gros oeuvre"}, format="json")
    assert rep.status_code == status.HTTP_409_CONFLICT, rep.content
    erreur = rep.json()["erreur"]
    assert erreur["code"] == "libelle_en_double"
    assert (
        erreur["message"]
        == "« gros oeuvre » figure déjà dans la liste (sous le libellé « Gros œuvre »)."
    )


def test_doublon_entre_deux_entrees_de_l_entreprise(client_dg):
    assert (
        client_dg.post(URL_TYPES, {"libelle": "Réhabilitation"}, format="json").status_code == 201
    )
    rep = client_dg.post(URL_TYPES, {"libelle": "  REHABILITATION "}, format="json")
    assert rep.status_code == status.HTTP_409_CONFLICT
    assert rep.json()["erreur"]["code"] == "libelle_en_double"
    assert "« Réhabilitation »" in rep.json()["erreur"]["message"]


def test_doublon_super_admin_creation(client_admin_plateforme):
    rep = client_admin_plateforme.post(URL_ADMIN_LOTS, {"libelle": "gros oeuvre"}, format="json")
    assert rep.status_code == status.HTTP_409_CONFLICT, rep.content
    erreur = rep.json()["erreur"]
    assert erreur["code"] == "libelle_en_double"
    assert "« Gros œuvre »" in erreur["message"]


def test_doublon_super_admin_modification(client_admin_plateforme):
    rep = client_admin_plateforme.post(
        URL_ADMIN_LOTS, {"libelle": "Lot de test doublon"}, format="json"
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    pk = rep.json()["id"]

    rep = client_admin_plateforme.patch(
        f"{URL_ADMIN_LOTS}{pk}/", {"libelle": "GROS OEUVRE"}, format="json"
    )
    assert rep.status_code == status.HTTP_409_CONFLICT, rep.content
    assert rep.json()["erreur"]["code"] == "libelle_en_double"


# --- Permission d'ajout ------------------------------------------------------


def test_ajout_refuse_sans_la_permission(client_ct):
    rep = client_ct.post(URL_TYPES, {"libelle": "Sans droit"}, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN, rep.content
    assert "erreur" in rep.json()


def test_ajout_accepte_une_fois_la_permission_attribuee(client_ct):
    _accorder("CT")
    rep = client_ct.post(URL_TYPES, {"libelle": "Avec droit"}, format="json")
    assert rep.status_code == status.HTTP_201_CREATED, rep.content


def test_ajout_accepte_au_dg(client_dg):
    rep = client_dg.post(URL_TYPES, {"libelle": "Ajout du DG"}, format="json")
    assert rep.status_code == status.HTTP_201_CREATED, rep.content


def test_projets_ecrire_ne_suffit_plus_pour_ajouter(client_ct):
    # Le CT a projets.ecrire par défaut, mais pas la permission d'ajout.
    rep = client_ct.post(URL_LOTS, {"libelle": "Lot du CT"}, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN


# --- Suppression réservée ----------------------------------------------------


def test_suppression_refusee_au_cp_meme_avec_la_permission_d_ajout(client_dg, client_cp):
    _accorder("CP")
    rep = client_cp.post(URL_TYPES, {"libelle": "Ajoutée par le CP"}, format="json")
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    code = rep.json()["code"]

    rep = client_cp.delete(f"{URL_TYPES}{code}/")
    assert rep.status_code == status.HTTP_403_FORBIDDEN, rep.content
    assert "erreur" in rep.json()
    assert any(e["code"] == code for e in client_dg.get(URL_TYPES).json())


def test_suppression_acceptee_au_dg(client_cp, client_dg):
    _accorder("CP")
    code = client_cp.post(URL_TYPES, {"libelle": "À retirer"}, format="json").json()["code"]
    assert client_dg.delete(f"{URL_TYPES}{code}/").status_code == status.HTTP_204_NO_CONTENT
    assert not any(e["code"] == code for e in client_dg.get(URL_TYPES).json())


def test_suppression_acceptee_a_l_administrateur(client_dg):
    code = client_dg.post(URL_TYPES, {"libelle": "Retrait par l'admin"}, format="json").json()[
        "code"
    ]
    client_ad = _client("ad.referentiels.droits@ccd-digital.ci", RoleGlobal.ADMIN)
    assert client_ad.delete(f"{URL_TYPES}{code}/").status_code == status.HTTP_204_NO_CONTENT


# --- Groupe ------------------------------------------------------------------


def test_groupe_enregistre_et_renvoye(client_dg):
    rep = client_dg.post(
        URL_LOTS, {"libelle": "Lot de test groupe", "groupe": "  Lots   spéciaux "}, format="json"
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    assert rep.json()["groupe"] == "Lots spéciaux"

    liste = client_dg.get(URL_LOTS).json()
    assert isinstance(liste, list)
    entree = next(e for e in liste if e["libelle"] == "Lot de test groupe")
    assert entree["groupe"] == "Lots spéciaux"
    assert entree["origine"] == "ENTREPRISE"


def test_groupe_optionnel(client_dg):
    rep = client_dg.post(URL_LOTS, {"libelle": "Lot sans groupe"}, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    assert rep.json()["groupe"] == ""


def test_groupe_trop_long_refuse(client_dg):
    rep = client_dg.post(
        URL_LOTS, {"libelle": "Lot groupe long", "groupe": "x" * 101}, format="json"
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST


# --- Route des droits --------------------------------------------------------


def test_droits_du_dg(client_dg):
    rep = client_dg.get(URL_DROITS)
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json() == {"peut_ajouter": True, "peut_retirer": True}


def test_droits_du_cp_ajout_sans_retrait(client_cp):
    _accorder("CP")
    assert client_cp.get(URL_DROITS).json() == {"peut_ajouter": True, "peut_retirer": False}


def test_droits_du_ct_sans_permission(client_ct):
    assert client_ct.get(URL_DROITS).json() == {"peut_ajouter": False, "peut_retirer": False}
