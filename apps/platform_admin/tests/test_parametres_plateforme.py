"""Tarifs des forfaits et identité de la plateforme : lecture publique, écriture du superviseur."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Plan
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.models.identite import IdentitePlateforme

HOTE = "localhost"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xb6\x1e\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def client_api():
    return APIClient(headers={"host": HOTE})


def _agent(email, superuser):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = Utilisateur.objects.create_superuser if superuser else Utilisateur.objects.create_user
        return fabrique(
            email=email,
            password="MotDePasse12345!",
            nom="Agent",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            **({} if superuser else {"is_staff": True}),
        )


@pytest.fixture
def forfaits(db):
    """Les trois forfaits vendables, avec des valeurs connues."""
    with schema_context(get_public_schema_name()):
        for code, libelle, prix in (
            (Plan.Code.BATISSEUR, "Bâtisseur", 2_900_000),
            (Plan.Code.MAITRE_OEUVRE, "Maître d'Œuvre", 6_500_000),
            (Plan.Code.PROMOTEUR, "Promoteur", 14_000_000),
        ):
            Plan.objects.update_or_create(
                code=code,
                defaults={"libelle": libelle, "prix_mensuel_montant": prix, "est_actif": True},
            )


def _corps_tarifs(**changements):
    base = {
        "plan_code": "BATISSEUR",
        "libelle": "Bâtisseur+",
        "prix_mensuel_centimes": 3_000_000,
        "prix_annuel_centimes": 30_000_000,
        "remise_annuelle_pourcent": 17,
        "limite_chantiers": 5,
        "limite_utilisateurs": None,
        "limite_stockage_go": 20,
        "avantages": [{"libelle": "Support par e-mail", "inclus": True}],
    }
    base.update(changements)
    return {"tarifs": [base]}


@pytest.mark.django_db
def test_tarifs_publics_sans_connexion(client_api, forfaits):
    reponse = client_api.get("/api/v1/plateforme/tarifs/")
    assert reponse.status_code == status.HTTP_200_OK
    codes = [t["plan_code"] for t in reponse.json()]
    assert codes == ["BATISSEUR", "MAITRE_OEUVRE", "PROMOTEUR"]
    assert set(reponse.json()[0]) == {
        "plan_code", "libelle", "prix_mensuel_centimes", "prix_annuel_centimes",
        "remise_annuelle_pourcent", "limite_chantiers", "limite_utilisateurs",
        "limite_stockage_go", "avantages",
    }


@pytest.mark.django_db
def test_superviseur_enregistre_les_tarifs_et_ils_sont_relus(client_api, forfaits):
    client_api.force_authenticate(user=_agent("sup.tarifs@ccd-digital.ci", superuser=True))
    reponse = client_api.put("/api/v1/admins/parametres/tarifs/", _corps_tarifs(), format="json")
    assert reponse.status_code == status.HTTP_200_OK, reponse.content

    lecture = APIClient(headers={"host": HOTE}).get("/api/v1/plateforme/tarifs/").json()
    batisseur = {t["plan_code"]: t for t in lecture}["BATISSEUR"]
    assert batisseur["libelle"] == "Bâtisseur+"
    assert batisseur["prix_mensuel_centimes"] == 3_000_000
    assert batisseur["remise_annuelle_pourcent"] == 17
    assert batisseur["limite_chantiers"] == 5
    assert batisseur["limite_utilisateurs"] is None
    assert batisseur["limite_stockage_go"] == 20
    assert batisseur["avantages"] == [{"libelle": "Support par e-mail", "inclus": True}]
    with schema_context(get_public_schema_name()):
        assert JournalPlateforme.objects.filter(action="MODIFICATION_TARIFS").exists()


@pytest.mark.django_db
def test_patch_est_un_alias_de_put_pour_les_tarifs(client_api, forfaits):
    """Le client HTTP du frontend n'expose que PATCH pour écrire : même effet que PUT."""
    client_api.force_authenticate(user=_agent("sup.patch@ccd-digital.ci", superuser=True))
    reponse = client_api.patch("/api/v1/admins/parametres/tarifs/", _corps_tarifs(libelle="Via PATCH"), format="json")
    assert reponse.status_code == status.HTTP_200_OK
    with schema_context(get_public_schema_name()):
        assert Plan.objects.get(code="BATISSEUR").libelle == "Via PATCH"


@pytest.mark.django_db
def test_agent_support_ne_peut_pas_modifier_les_tarifs(client_api, forfaits):
    client_api.force_authenticate(user=_agent("support.tarifs@ccd-digital.ci", superuser=False))
    reponse = client_api.put("/api/v1/admins/parametres/tarifs/", _corps_tarifs(), format="json")
    assert reponse.status_code == status.HTTP_403_FORBIDDEN
    with schema_context(get_public_schema_name()):
        assert Plan.objects.get(code="BATISSEUR").libelle == "Bâtisseur"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changement",
    [
        {"prix_mensuel_centimes": 0},
        {"remise_annuelle_pourcent": 101},
        {"plan_code": "STARTER"},
        {"limite_stockage_go": 0},
    ],
)
def test_tarifs_invalides_refuses_sans_rien_ecrire(client_api, forfaits, changement):
    client_api.force_authenticate(user=_agent("sup.invalide@ccd-digital.ci", superuser=True))
    reponse = client_api.put("/api/v1/admins/parametres/tarifs/", _corps_tarifs(**changement), format="json")
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST
    with schema_context(get_public_schema_name()):
        assert Plan.objects.get(code="BATISSEUR").prix_mensuel_montant == 2_900_000


@pytest.mark.django_db
def test_identite_publique_par_defaut_puis_modifiee(client_api):
    with schema_context(get_public_schema_name()):
        IdentitePlateforme.objects.all().delete()
    avant = client_api.get("/api/v1/plateforme/identite/").json()
    assert avant == {"nom": "CCD Digital", "logo_url": None}

    client_api.force_authenticate(user=_agent("sup.identite@ccd-digital.ci", superuser=True))
    reponse = client_api.patch(
        "/api/v1/admins/parametres/identite/",
        {"nom": "Soumafe BTP", "logo": SimpleUploadedFile("logo.png", PNG, content_type="image/png")},
        format="multipart",
    )
    assert reponse.status_code == status.HTTP_200_OK, reponse.content
    assert reponse.json()["nom"] == "Soumafe BTP"
    assert reponse.json()["logo_url"]

    public = APIClient(headers={"host": HOTE}).get("/api/v1/plateforme/identite/").json()
    assert public["nom"] == "Soumafe BTP" and public["logo_url"]

    retrait = client_api.patch("/api/v1/admins/parametres/identite/", {"retirer_logo": "true"}, format="multipart")
    assert retrait.status_code == status.HTTP_200_OK
    assert retrait.json()["logo_url"] is None and retrait.json()["nom"] == "Soumafe BTP"


@pytest.mark.django_db
def test_identite_refuse_nom_vide_fichier_non_image_et_support(client_api):
    client_api.force_authenticate(user=_agent("sup.refus@ccd-digital.ci", superuser=True))
    assert client_api.patch("/api/v1/admins/parametres/identite/", {"nom": "  "}, format="multipart").status_code == 400
    texte = SimpleUploadedFile("logo.txt", b"pas une image", content_type="text/plain")
    assert client_api.patch("/api/v1/admins/parametres/identite/", {"logo": texte}, format="multipart").status_code == 400

    client_api.force_authenticate(user=_agent("support.refus@ccd-digital.ci", superuser=False))
    assert client_api.patch("/api/v1/admins/parametres/identite/", {"nom": "X"}, format="multipart").status_code == 403
