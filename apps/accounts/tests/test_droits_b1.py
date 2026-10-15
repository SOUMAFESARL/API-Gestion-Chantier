"""B1 du chantier « droits » (16/10/2026) : ce que l'écran des rôles attend du serveur.

- un rôle créé avec sa matrice `permissions_modules` garde ses droits (la valeur par défaut de
  `permissions` les écrasait) ;
- la liste explicite `permissions` reste la forme qui l'emporte quand elle est envoyée ;
- le 409 « confirmation requise » porte l'enveloppe d'erreur du produit ;
- le profil dit la portée du rôle ;
- le rattachement des permissions d'un module s'accepte aussi en PATCH (back-office) ;
- créer un module ou lui retirer une permission ne plante plus (relation `permissions` disparue).
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.catalogue.models import CataloguePermission
from apps.core.enums import RoleGlobal, StatutUtilisateur

pytestmark = pytest.mark.django_db

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def roles(schema_demo):
    from apps.accounts.services.roles import initialiser_roles_par_defaut

    initialiser_roles_par_defaut()


def _utilisateur(email, code_role):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email=email).delete()
        role = Role.objects.get(code=code_role, supprime_le__isnull=True)
        globaux = {
            "DG": RoleGlobal.DIRECTEUR_GENERAL,
            "AD": RoleGlobal.ADMIN,
            "CP": RoleGlobal.CHEF_PROJET,
        }
        utilisateur = Utilisateur.objects.create_user(
            email=email,
            password="MotDePasse12345!",
            nom=code_role,
            prenom="B1",
            role_global=globaux.get(code_role, RoleGlobal.VISITEUR),
            statut=StatutUtilisateur.ACTIF,
        )
        utilisateur.role = role
        if code_role == "DG":
            utilisateur.is_owner = True
        utilisateur.save()
        return utilisateur


@pytest.fixture
def client_dg(roles):
    client = APIClient(HTTP_HOST=HOTE)
    client.force_authenticate(_utilisateur("dg.b1@demo.ci", "DG"))
    return client


def _droits_en_base(role_id):
    with schema_context(SCHEMA):
        return {
            rmp.module.code: (
                rmp.niveau,
                sorted(rmp.permissions_catalogue.values_list("code", flat=True)),
            )
            for rmp in RoleModulePermission.objects.filter(role_id=role_id).select_related("module")
        }


def test_creation_avec_matrice_garde_ses_droits(client_dg):
    reponse = client_dg.post(
        "/api/v1/parametres/roles/",
        {
            "code": "B1_MATRICE",
            "libelle": "Matrice B1",
            "permissions_modules": {"projets": ["lecture", "saisie"], "chantier": ["lecture"]},
        },
        format="json",
    )
    assert reponse.status_code == 201, reponse.content
    droits = _droits_en_base(reponse.json()["id"])
    assert droits["projets"][0] == 2
    assert "projets.ecrire" in droits["projets"][1]
    assert droits["chantier"][0] == 1


def test_creation_avec_liste_explicite_de_codes(client_dg):
    reponse = client_dg.post(
        "/api/v1/parametres/roles/",
        {
            "code": "B1_CODES",
            "libelle": "Codes B1",
            "permissions": ["projets.lire", "projets.voir_montants"],
        },
        format="json",
    )
    assert reponse.status_code == 201, reponse.content
    codes = _droits_en_base(reponse.json()["id"])["projets"][1]
    assert codes == ["projets.lire", "projets.voir_montants"]


def test_liste_vide_explicite_ne_donne_rien(client_dg):
    reponse = client_dg.post(
        "/api/v1/parametres/roles/",
        {
            "code": "B1_VIDE",
            "libelle": "Vide B1",
            "permissions": [],
            "permissions_modules": {"projets": ["lecture"]},
        },
        format="json",
    )
    assert reponse.status_code == 201, reponse.content
    assert all(niveau == 0 for niveau, _ in _droits_en_base(reponse.json()["id"]).values())


def test_modification_par_liste_complete_remplace_la_matrice(client_dg):
    creation = client_dg.post(
        "/api/v1/parametres/roles/",
        {"code": "B1_REMPLACE", "libelle": "Remplacé B1", "permissions": ["projets.lire"]},
        format="json",
    )
    assert creation.status_code == 201, creation.content
    role_id = creation.json()["id"]

    reponse = client_dg.patch(
        f"/api/v1/parametres/roles/{role_id}/",
        {"permissions": ["chantier.lire", "chantier.rediger"]},
        format="json",
    )
    assert reponse.status_code == 200, reponse.content
    droits = _droits_en_base(role_id)
    assert droits["projets"] == (0, [])
    assert droits["chantier"][1] == ["chantier.lire", "chantier.rediger"]


def test_description_enregistree(client_dg):
    creation = client_dg.post(
        "/api/v1/parametres/roles/",
        {"code": "B1_DESC", "libelle": "Desc B1", "description": "Première description"},
        format="json",
    )
    assert creation.status_code == 201, creation.content
    role_id = creation.json()["id"]
    client_dg.patch(
        f"/api/v1/parametres/roles/{role_id}/",
        {"description": "Seconde description"},
        format="json",
    )
    with schema_context(SCHEMA):
        assert Role.objects.get(pk=role_id).description == "Seconde description"


def test_confirmation_requise_au_format_du_produit(client_dg):
    creation = client_dg.post(
        "/api/v1/parametres/roles/",
        {"code": "B1_PORTEE", "libelle": "Portée B1", "portee": "PROJET"},
        format="json",
    )
    assert creation.status_code == 201, creation.content
    reponse = client_dg.patch(
        f"/api/v1/parametres/roles/{creation.json()['id']}/",
        {"portee": "ENTREPRISE"},
        format="json",
    )
    assert reponse.status_code == 409
    corps = reponse.json()
    assert corps["code"] == "confirmation_requise"  # clé historique, gardée
    assert corps["erreur"]["code"] == "confirmation_requise"
    assert "personnes_touchees" in corps["erreur"]["details"]


@pytest.mark.parametrize(("code_role", "attendue"), [("DG", "ENTREPRISE"), ("CP", "PROJET")])
def test_profil_dit_la_portee(roles, code_role, attendue):
    client = APIClient(HTTP_HOST=HOTE)
    client.force_authenticate(_utilisateur(f"portee.{code_role.lower()}@demo.ci", code_role))
    corps = client.get("/api/v1/auth/profil/").json()
    assert corps["portee"] == attendue
    assert isinstance(corps["permissions"], list)


def test_rattachement_des_permissions_d_un_module_en_patch(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    with schema_context(get_public_schema_name()):
        # Codes propres au test : LECTURE et ECRITURE sont supprimés logiquement du catalogue.
        for code in ("B1_LIRE", "B1_ECRIRE"):
            CataloguePermission.objects.get_or_create(code=code, defaults={"libelle": code})
        Utilisateur.tous_objets.filter(email="superviseur.b1@ccd-digital.ci").delete()
        superviseur = Utilisateur.objects.create_superuser(
            email="superviseur.b1@ccd-digital.ci",
            password="MotDePasse12345!",
            nom="Superviseur",
            prenom="B1",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(HTTP_HOST="localhost")
    client.force_authenticate(superviseur)
    creation = client.post(
        "/api/v1/admins/modules/",
        {"code": "b1_module", "libelle": "Module B1", "permissions": ["B1_LIRE"]},
        format="json",
    )
    assert creation.status_code == 201, creation.content
    assert creation.json()["permissions_codes"] == ["B1_LIRE"]

    reponse = client.patch(
        f"/api/v1/admins/modules/{creation.json()['id']}/permissions/",
        {"permissions": ["B1_LIRE", "B1_ECRIRE"]},
        format="json",
    )
    assert reponse.status_code == 200, reponse.content
    assert sorted(reponse.json()["permissions_codes"]) == ["B1_ECRIRE", "B1_LIRE"]

    # Le retrait d'une permission révoque sans erreur (chemin de révocation des rôles).
    retrait = client.patch(
        f"/api/v1/admins/modules/{creation.json()['id']}/permissions/",
        {"permissions": ["B1_LIRE"]},
        format="json",
    )
    assert retrait.status_code == 200, retrait.content
    assert retrait.json()["permissions_codes"] == ["B1_LIRE"]

    # `acces_par_defaut`, que l'écran du back-office envoie à chaque modification, ne remplace
    # plus les permissions du module.
    modification = client.patch(
        f"/api/v1/admins/modules/{creation.json()['id']}/",
        {"description": "Nouvelle description", "acces_par_defaut": ["lecture", "saisie"]},
        format="json",
    )
    assert modification.status_code == 200, modification.content
    assert modification.json()["permissions_codes"] == ["B1_LIRE"]
    assert modification.json()["description"] == "Nouvelle description"
