"""Le mode d'exécution d'un lot est un référentiel, rattaché à un mode de base."""

from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import get_public_schema_name, schema_context
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.catalogue.models import ReferentielPlateforme
from apps.chantier.selectors.journal import contexte_projet
from apps.chantier.services.journal import aujourdhui
from apps.chantier.tests.test_journal_api import API, corps, terrain  # noqa: F401
from apps.core.enums import ModeExecution, RoleGlobal, StatutUtilisateur
from apps.projets.models import Activite, Lot, ReferentielEntreprise
from apps.projets.serializers import LotCreationProjetSerializer
from apps.projets.services.lots import lire_excel
from apps.projets.services.referentiels import (
    code_mode_execution_valide,
    libelle_mode_execution,
    mode_base,
    table_modes_execution,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/referentiels/modes-execution/"
URL_ADMIN = "/api/v1/admins/referentiels/modes-execution/"
BASES = ["REGIE", "SOUS_TRAITANCE_STRUCTUREE", "SOUS_TRAITANCE_INFORMELLE"]


@pytest.fixture
def client_dg(schema_demo):
    user = Utilisateur.objects.create_user(
        email=f"dg.modes-{uuid4().hex[:8]}@demo.ci",
        password="Test12345!",
        nom="DG",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    return client


@pytest.fixture
def client_admin(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superviseur.modes@ccd-digital.ci").delete()
        admin = Utilisateur.objects.create_superuser(
            email="superviseur.modes@ccd-digital.ci",
            password="MotDePasse12345!",
            nom="Superviseur",
            prenom="Modes",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(HTTP_HOST="localhost")
    client.force_authenticate(admin)
    return client


def _ajouter(client, libelle, groupe):
    return client.post(URL, {"libelle": libelle, "groupe": groupe}, format="json")


def _lot_payload(mode, nom="Lot"):
    return {"nom": nom, "mode_execution": mode, "type_bordereau": "FORFAIT"}


# --- Le référentiel -----------------------------------------------------------------------


def test_les_trois_modes_de_base_viennent_de_la_plateforme(client_dg):
    modes = client_dg.get(URL).json()
    for code in BASES:
        entree = next(e for e in modes if e["code"] == code)
        assert entree["origine"] == "PLATEFORME"
        assert entree["groupe"] == code
    libelles = {e["code"]: e["libelle"] for e in modes}
    assert libelles["REGIE"] == "Régie"
    assert libelles["SOUS_TRAITANCE_INFORMELLE"] == "Sous-traitance informelle"


def test_liste_fusionnee_plateforme_puis_entreprise(client_dg):
    rep = _ajouter(client_dg, "Groupement momentané", "SOUS_TRAITANCE_STRUCTUREE")
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    assert rep.json() == {
        "code": "GROUPEMENT_MOMENTANE",
        "libelle": "Groupement momentané",
        "groupe": "SOUS_TRAITANCE_STRUCTUREE",
        "origine": "ENTREPRISE",
    }
    modes = client_dg.get(URL).json()
    assert [e["origine"] for e in modes] == ["PLATEFORME"] * 3 + ["ENTREPRISE"]


@pytest.mark.parametrize("groupe", ["", "REGIE_DIRECTE", "Régie", "AUTRE"])
def test_ajout_entreprise_refuse_un_groupe_qui_n_est_pas_un_mode_de_base(client_dg, groupe):
    rep = _ajouter(client_dg, "Mode sans base", groupe)
    assert rep.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, rep.content
    assert "mode de base" in rep.json()["erreur"]["message"]
    assert not ReferentielEntreprise.objects.filter(libelle="Mode sans base").exists()


def test_retrait_reserve_aux_entrees_de_l_entreprise(client_dg):
    _ajouter(client_dg, "Cotraitance", "REGIE")
    assert client_dg.delete(f"{URL}COTRAITANCE/").status_code == status.HTTP_204_NO_CONTENT
    assert client_dg.delete(f"{URL}REGIE/").status_code == status.HTTP_400_BAD_REQUEST


def test_super_admin_ajoute_un_mode_propose_a_toutes_les_entreprises(client_admin, client_dg):
    rep = client_admin.post(
        URL_ADMIN,
        {"libelle": "Régie assistée", "groupe": "REGIE"},
        format="json",
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    pk = rep.json()["id"]
    assert any(
        e["code"] == "REGIE_ASSISTEE" and e["origine"] == "PLATEFORME"
        for e in client_dg.get(URL).json()
    )
    assert len(client_admin.get(URL_ADMIN).json()) == 4

    refus = client_admin.post(URL_ADMIN, {"libelle": "Sans base", "groupe": "X"}, format="json")
    assert refus.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    refus = client_admin.patch(
        f"{URL_ADMIN}{pk}/", {"libelle": "Régie assistée", "groupe": ""}, format="json"
    )
    assert refus.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    assert client_admin.delete(f"{URL_ADMIN}{pk}/").status_code == status.HTTP_204_NO_CONTENT
    with schema_context(get_public_schema_name()):
        assert not ReferentielPlateforme.objects.filter(pk=pk).exists()


# --- mode_base ----------------------------------------------------------------------------


def test_mode_base(client_dg):
    _ajouter(client_dg, "Tâcheronnage", "SOUS_TRAITANCE_INFORMELLE")
    for code in BASES:
        assert mode_base(code) == code
    assert mode_base("TACHERONNAGE") == "SOUS_TRAITANCE_INFORMELLE"
    assert mode_base("CODE_RETIRE_OU_INCONNU") == ModeExecution.REGIE


def test_la_table_des_modes_se_calcule_une_fois_par_cache(schema_demo):
    cache = {}
    with CaptureQueriesContext(connection) as premiere:
        table = table_modes_execution(cache)
    with CaptureQueriesContext(connection) as seconde:
        assert table_modes_execution(cache) is table
    lectures = [q for q in premiere.captured_queries if "referentiel" in q["sql"]]
    assert len(lectures) == 4  # plateforme et entreprise, chacune actives puis retirées
    assert not [q for q in seconde.captured_queries if "referentiel" in q["sql"]]


def test_la_validation_lit_le_referentiel_une_fois_pour_tous_les_lots(schema_demo):
    """Création v2 : cinq lots dans un même serializer, une seule lecture de la table."""
    donnees = [{"libelle": f"Lot {n}", "mode_execution": "REGIE"} for n in range(5)]
    with CaptureQueriesContext(connection) as requetes:
        serializer = LotCreationProjetSerializer(data=donnees, many=True)
        assert serializer.is_valid(), serializer.errors
    sur_le_referentiel = [
        q for q in requetes.captured_queries if "referentiel_entreprise" in q["sql"]
    ]
    assert len(sur_le_referentiel) <= 2


def test_l_import_excel_lit_le_referentiel_une_fois_pour_toutes_les_lignes(schema_demo):
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(["nom", "mode_execution"])
    for numero in range(5):
        feuille.append([f"Lot {numero}", "REGIE"])
    tampon = BytesIO()
    classeur.save(tampon)
    fichier = SimpleUploadedFile("lots.xlsx", tampon.getvalue())
    with CaptureQueriesContext(connection) as requetes:
        lots = lire_excel(fichier)
    assert len(lots) == 5
    sur_le_referentiel = [
        q for q in requetes.captured_queries if "referentiel_entreprise" in q["sql"]
    ]
    assert len(sur_le_referentiel) <= 2


# --- Le lot -------------------------------------------------------------------------------


def test_lot_avec_un_mode_d_entreprise(terrain, client_dg):  # noqa: F811
    _ajouter(client_dg, "Tâcheronnage", "SOUS_TRAITANCE_INFORMELLE")
    cp = terrain["clients"]["CP"]
    rep = cp.post(
        f"/api/v1/projets/{terrain['projet'].pk}/lots/",
        _lot_payload("TACHERONNAGE"),
        format="json",
    )
    assert rep.status_code == status.HTTP_201_CREATED, rep.content
    assert rep.json()["mode_execution"] == "TACHERONNAGE"
    assert rep.json()["mode_execution_libelle"] == "Tâcheronnage"

    liste = cp.get(f"/api/v1/projets/{terrain['projet'].pk}/lots/").json()
    libelles = {lot["mode_execution"]: lot["mode_execution_libelle"] for lot in liste}
    assert libelles == {"REGIE": "Régie", "TACHERONNAGE": "Tâcheronnage"}


def test_lot_avec_un_code_inconnu_est_refuse(terrain):  # noqa: F811
    cp = terrain["clients"]["CP"]
    rep = cp.post(
        f"/api/v1/projets/{terrain['projet'].pk}/lots/",
        _lot_payload("MODE_INVENTE"),
        format="json",
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert "mode_execution" in rep.json()["erreur"]["details"]
    assert not Lot.objects.filter(mode_execution="MODE_INVENTE").exists()


def test_un_code_retire_reste_valide_tant_qu_un_lot_le_porte(terrain, client_dg):  # noqa: F811
    _ajouter(client_dg, "Cotraitance", "SOUS_TRAITANCE_STRUCTUREE")
    assert code_mode_execution_valide("COTRAITANCE")
    Lot.objects.create(
        projet=terrain["projet"], code="L-09", libelle="Cotraité", mode_execution="COTRAITANCE"
    )
    client_dg.delete(f"{URL}COTRAITANCE/")
    assert code_mode_execution_valide("COTRAITANCE")
    assert not code_mode_execution_valide("AUTRE_RETIRE")


# --- Le rapport journalier ----------------------------------------------------------------


def test_un_mode_d_entreprise_donne_les_sections_de_son_mode_de_base(terrain, client_dg):  # noqa: F811
    _ajouter(client_dg, "Tâcheronnage", "SOUS_TRAITANCE_INFORMELLE")
    projet = terrain["projet"]
    lot = Lot.objects.create(
        projet=projet, code="L-02", libelle="Peinture", mode_execution="TACHERONNAGE"
    )
    Activite.objects.create(lot=lot, libelle="Peinture", quantite_prevue=50, unite="M2")

    contexte = contexte_projet(projet, aujourdhui())

    assert "PRODUCTION" in contexte["sections"]
    assert "AVANCEMENT" in contexte["sections"]  # le lot de régie du terrain
    charge = next(c for c in contexte["lots"] if c["id"] == str(lot.id))
    assert charge["mode_execution"] == "SOUS_TRAITANCE_INFORMELLE"
    assert charge["mode_execution_libelle"] == "Tâcheronnage"
    suivi = {a["lot_id"]: a["suivi"] for a in contexte["activites"]}
    assert suivi[str(lot.id)] == "PRODUCTION"
    assert suivi[str(terrain["lot"].id)] == "AVANCEMENT"


def test_le_contexte_du_journal_lit_les_modes_une_fois(terrain, client_dg):  # noqa: F811
    _ajouter(client_dg, "Tâcheronnage", "SOUS_TRAITANCE_INFORMELLE")
    projet = terrain["projet"]
    for numero in range(2, 6):
        Lot.objects.create(
            projet=projet,
            code=f"L-{numero:02d}",
            libelle=f"Lot {numero}",
            mode_execution="TACHERONNAGE",
        )
    with CaptureQueriesContext(connection) as requetes:
        contexte_projet(projet, aujourdhui())
    sur_le_referentiel = [
        q for q in requetes.captured_queries if "referentiel_entreprise" in q["sql"]
    ]
    assert len(sur_le_referentiel) == 2  # actives + retirées, quel que soit le nombre de lots


def test_une_entree_retiree_garde_son_mode_de_base_pour_les_lots_qui_la_portent(
    terrain,  # noqa: F811
    client_dg,
):
    _ajouter(client_dg, "Tâcheronnage", "SOUS_TRAITANCE_INFORMELLE")
    projet = terrain["projet"]
    lot = Lot.objects.create(
        projet=projet, code="L-02", libelle="Peinture", mode_execution="TACHERONNAGE"
    )
    Activite.objects.create(lot=lot, libelle="Peinture", quantite_prevue=50, unite="M2")

    assert client_dg.delete(f"{URL}TACHERONNAGE/").status_code == status.HTTP_204_NO_CONTENT
    assert all(e["code"] != "TACHERONNAGE" for e in client_dg.get(URL).json())

    assert mode_base("TACHERONNAGE") == ModeExecution.SOUS_TRAITANCE_INFORMELLE
    assert libelle_mode_execution("TACHERONNAGE") == "Tâcheronnage"
    assert code_mode_execution_valide("TACHERONNAGE")  # un lot le porte encore

    contexte = contexte_projet(projet, aujourdhui())
    assert "PRODUCTION" in contexte["sections"]
    charge = next(c for c in contexte["lots"] if c["id"] == str(lot.id))
    assert charge["mode_execution"] == "SOUS_TRAITANCE_INFORMELLE"
    assert charge["mode_execution_libelle"] == "Tâcheronnage"
    suivi = {a["lot_id"]: a["suivi"] for a in contexte["activites"]}
    assert suivi[str(lot.id)] == "PRODUCTION"


def test_un_lot_d_entreprise_informelle_ne_se_declare_pas_en_avancement(terrain, client_dg):  # noqa: F811
    _ajouter(client_dg, "Tâcheronnage", "SOUS_TRAITANCE_INFORMELLE")
    lot = Lot.objects.create(
        projet=terrain["projet"], code="L-02", libelle="Peinture", mode_execution="TACHERONNAGE"
    )
    donnees = corps(
        terrain,
        lots_travailles=[{"lot_id": str(lot.id), "observation": "Peinture des cloisons"}],
    )
    rep = terrain["clients"]["CC"].post(f"{API}/rapports/", donnees, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST, rep.content
