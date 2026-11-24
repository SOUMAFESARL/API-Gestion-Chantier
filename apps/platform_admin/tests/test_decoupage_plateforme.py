"""Tests du CRUD Super Admin des listes et modèles de découpage plateforme."""

from __future__ import annotations

import io
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.authentification import emettre_jetons
from apps.catalogue.models import (
    CategorieReferentiel,
    LigneModelePlateforme,
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    NiveauModelePlateforme,
    ReferentielPlateforme,
    ValeurListePlateforme,
)
from apps.core.contexte import contexte_entreprise, reinitialiser_contexte
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutProjet, StatutUtilisateur
from apps.entreprises.models import Entreprise
from apps.platform_admin.models import JournalPlateforme
from apps.projets.models import (
    ModeleDecoupageEntreprise,
    NiveauModeleEntreprise,
    NiveauProjet,
    Projet,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _contexte_propre():
    reinitialiser_contexte()
    yield
    reinitialiser_contexte()


def _client_pour(utilisateur: Utilisateur) -> APIClient:
    jeton = emettre_jetons(utilisateur)["access"]
    client = APIClient(HTTP_HOST="localhost")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {jeton}")
    return client


@pytest.fixture
def types_projet_plateforme():
    codes = [
        ("BATIMENT", "Bâtiment"),
        ("ROUTE", "Route"),
        ("TP_GENIE_CIVIL", "TP — Génie civil"),
    ]
    crees = {}
    for ordre, (code, libelle) in enumerate(codes, start=1):
        obj, _ = ReferentielPlateforme.objects.get_or_create(
            categorie=CategorieReferentiel.TYPE_PROJET,
            code=code,
            defaults={"libelle": libelle, "ordre": ordre},
        )
        crees[code] = obj
    return crees


@pytest.fixture
def superviseur() -> Utilisateur:
    return Utilisateur.objects.create_superuser(
        email=f"sup-{uuid.uuid4().hex[:8]}@ccd-plateforme.ci",
        password="TestPassword123!",
        nom="Superviseur",
        prenom="Plateforme",
    )


@pytest.fixture
def support() -> Utilisateur:
    return Utilisateur.objects.create_user(
        email=f"support-{uuid.uuid4().hex[:8]}@ccd-plateforme.ci",
        password="TestPassword123!",
        nom="Support",
        prenom="Plateforme",
        role_global=RoleGlobal.ADMIN,
        is_staff=True,
        is_superuser=False,
        statut=StatutUtilisateur.ACTIF,
    )


@pytest.fixture
def utilisateur_entreprise():
    slug = f"ent-{uuid.uuid4().hex[:6]}"
    ent = Entreprise.objects.create(
        slug=slug,
        raison_sociale=f"Entreprise {slug}",
        email_contact=f"contact@{slug}.ci",
        statut=StatutEntreprise.ACTIF,
    )
    with contexte_entreprise(ent):
        user = Utilisateur.objects.create_user(
            email=f"dg@{slug}.ci",
            password="TestPassword123!",
            nom="Directeur",
            prenom="Test",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        user.is_owner = True
        user.save(update_fields=["is_owner", "modifie_le"])
    return ent, user


def _creer_entreprise_et_dg(prefixe: str) -> tuple[Entreprise, Utilisateur]:
    slug = f"{prefixe}-{uuid.uuid4().hex[:6]}"
    ent = Entreprise.objects.create(
        slug=slug,
        raison_sociale=f"Société {slug}",
        email_contact=f"contact@{slug}.ci",
        statut=StatutEntreprise.ACTIF,
    )
    with contexte_entreprise(ent):
        dg = Utilisateur.objects.create_user(
            email=f"dg@{slug}.ci",
            password="TestPassword123!",
            nom="DG",
            prenom=prefixe.capitalize(),
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        dg.is_owner = True
        dg.save(update_fields=["is_owner", "modifie_le"])
    return ent, dg


def _payload_modele(nom: str, liste_id: str | None = None) -> dict:
    niveau_lot = {"libelle": "Lot", "liste": None, "alerter": True}
    if liste_id:
        niveau_lot["liste"] = {"origine": "PLATEFORME", "id": liste_id}
    return {
        "nom": nom,
        "description": "Gabarit de référence",
        "types_projet": ["BATIMENT"],
        "par_defaut_pour": ["BATIMENT"],
        "est_actif": True,
        "niveaux": [
            {"libelle": "Phase", "liste": None, "alerter": False},
            niveau_lot,
            {"libelle": "Activité", "liste": None, "alerter": False},
        ],
        "lignes": [
            ["Fondations", "Gros œuvre", "Terrassement"],
            ["Fondations", "Gros œuvre", "Semelles"],
        ],
    }


# --------------------------------------------------------------------------
# 1. Permissions : SUPERVISEUR vs SUPPORT vs Entreprise
# --------------------------------------------------------------------------
class TestPermissionsDecoupagePlateforme:
    def test_superviseur_a_acces_crud_complet(self, superviseur, types_projet_plateforme):
        client = _client_pour(superviseur)

        # Création & lecture liste
        rep_liste = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Lots QA", "description": "Liste QA", "valeurs": ["Gros œuvre"]},
            format="json",
        )
        assert rep_liste.status_code == 201, rep_liste.content
        liste_id = rep_liste.json()["id"]

        assert client.get("/api/v1/admins/decoupage/listes/").status_code == 200
        assert client.get(f"/api/v1/admins/decoupage/listes/{liste_id}/").status_code == 200

        # Création, lecture, modification, actions rapides et suppression modèle
        rep_modele = client.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle Superviseur QA", liste_id=liste_id),
            format="json",
        )
        assert rep_modele.status_code == 201, rep_modele.content
        modele_id = rep_modele.json()["id"]

        assert client.get("/api/v1/admins/decoupage/modeles/").status_code == 200
        assert client.get(f"/api/v1/admins/decoupage/modeles/{modele_id}/").status_code == 200
        assert (
            client.patch(
                f"/api/v1/admins/decoupage/modeles/{modele_id}/",
                {"description": "Maj"},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/desactiver/").status_code
            == 200
        )
        assert (
            client.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/activer/").status_code == 200
        )
        rep_dup = client.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/dupliquer/")
        assert rep_dup.status_code == 201
        dup_id = rep_dup.json()["id"]

        assert client.delete(f"/api/v1/admins/decoupage/modeles/{dup_id}/").status_code == 204
        assert client.delete(f"/api/v1/admins/decoupage/modeles/{modele_id}/").status_code == 204
        assert client.delete(f"/api/v1/admins/decoupage/listes/{liste_id}/").status_code == 204

    def test_support_lit_mais_recoit_403_en_ecriture(
        self, superviseur, support, types_projet_plateforme
    ):
        sup_client = _client_pour(superviseur)
        liste_id = sup_client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Lots Support QA", "valeurs": ["Lot A"]},
            format="json",
        ).json()["id"]
        val_id = sup_client.get(f"/api/v1/admins/decoupage/listes/{liste_id}/").json()["valeurs"][
            0
        ]["id"]
        modele_id = sup_client.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle Support QA", liste_id=liste_id),
            format="json",
        ).json()["id"]

        client_sup = _client_pour(support)

        # Lectures autorisées (200)
        assert client_sup.get("/api/v1/admins/decoupage/listes/").status_code == 200
        assert client_sup.get(f"/api/v1/admins/decoupage/listes/{liste_id}/").status_code == 200
        assert client_sup.get("/api/v1/admins/decoupage/listes/modele-excel/").status_code == 200
        assert client_sup.get("/api/v1/admins/decoupage/modeles/").status_code == 200
        assert client_sup.get(f"/api/v1/admins/decoupage/modeles/{modele_id}/").status_code == 200
        assert client_sup.get("/api/v1/admins/decoupage/modeles/modele-excel/").status_code == 200

        # Écritures interdites (403) sur modèles
        payload = _payload_modele("Tentative Support", liste_id=liste_id)
        assert (
            client_sup.post("/api/v1/admins/decoupage/modeles/", payload, format="json").status_code
            == 403
        )
        assert (
            client_sup.put(
                f"/api/v1/admins/decoupage/modeles/{modele_id}/", payload, format="json"
            ).status_code
            == 403
        )
        assert (
            client_sup.patch(
                f"/api/v1/admins/decoupage/modeles/{modele_id}/",
                {"description": "X"},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_sup.delete(f"/api/v1/admins/decoupage/modeles/{modele_id}/").status_code == 403
        )
        assert (
            client_sup.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/activer/").status_code
            == 403
        )
        assert (
            client_sup.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/desactiver/").status_code
            == 403
        )
        assert (
            client_sup.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/dupliquer/").status_code
            == 403
        )

        csv_file = SimpleUploadedFile("m.csv", b"Phase;Lot\nP1;L1\n", content_type="text/csv")
        assert (
            client_sup.post(
                "/api/v1/admins/decoupage/modeles/importer-fichier/",
                {"fichier": csv_file},
                format="multipart",
            ).status_code
            == 403
        )

        # Écritures interdites (403) sur listes & valeurs
        assert (
            client_sup.post(
                "/api/v1/admins/decoupage/listes/", {"libelle": "X"}, format="json"
            ).status_code
            == 403
        )
        assert (
            client_sup.patch(
                f"/api/v1/admins/decoupage/listes/{liste_id}/", {"description": "X"}, format="json"
            ).status_code
            == 403
        )
        assert client_sup.delete(f"/api/v1/admins/decoupage/listes/{liste_id}/").status_code == 403
        assert (
            client_sup.post(f"/api/v1/admins/decoupage/listes/{liste_id}/activer/").status_code
            == 403
        )
        assert (
            client_sup.post(f"/api/v1/admins/decoupage/listes/{liste_id}/desactiver/").status_code
            == 403
        )
        assert (
            client_sup.post(
                f"/api/v1/admins/decoupage/listes/{liste_id}/valeurs/",
                {"valeurs": ["V2"]},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_sup.patch(
                f"/api/v1/admins/decoupage/valeurs/{val_id}/", {"libelle": "V1b"}, format="json"
            ).status_code
            == 403
        )
        assert client_sup.delete(f"/api/v1/admins/decoupage/valeurs/{val_id}/").status_code == 403

    def test_utilisateur_entreprise_recoit_403_sur_routes_admins(
        self, superviseur, utilisateur_entreprise, types_projet_plateforme
    ):
        sup_client = _client_pour(superviseur)
        liste_id = sup_client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Liste Isolée", "valeurs": ["A"]},
            format="json",
        ).json()["id"]
        modele_id = sup_client.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle Isolé", liste_id=liste_id),
            format="json",
        ).json()["id"]

        _, user_ent = utilisateur_entreprise
        ent_client = _client_pour(user_ent)

        for method, url in [
            ("get", "/api/v1/admins/decoupage/listes/"),
            ("post", "/api/v1/admins/decoupage/listes/"),
            ("get", f"/api/v1/admins/decoupage/listes/{liste_id}/"),
            ("post", f"/api/v1/admins/decoupage/listes/{liste_id}/activer/"),
            ("get", "/api/v1/admins/decoupage/modeles/"),
            ("post", "/api/v1/admins/decoupage/modeles/"),
            ("get", f"/api/v1/admins/decoupage/modeles/{modele_id}/"),
            ("patch", f"/api/v1/admins/decoupage/modeles/{modele_id}/"),
            ("delete", f"/api/v1/admins/decoupage/modeles/{modele_id}/"),
            ("post", f"/api/v1/admins/decoupage/modeles/{modele_id}/dupliquer/"),
        ]:
            rep = getattr(ent_client, method)(url, {}, format="json")
            assert rep.status_code == 403, f"{method.upper()} {url} → {rep.status_code}"


# --------------------------------------------------------------------------
# 2. CRUD modèles, filtres, versioning sélectif & actions rapides
# --------------------------------------------------------------------------
class TestCrudModelesPlateforme:
    def test_filtres_patch_partiel_et_versioning_selectif(
        self, superviseur, types_projet_plateforme
    ):
        client = _client_pour(superviseur)

        # Créer deux modèles avec types et statuts distincts
        rep_a = client.post(
            "/api/v1/admins/decoupage/modeles/",
            {
                **_payload_modele("Résidentiel Élevé"),
                "description": "Gabarit bâtiment béton",
                "types_projet": ["BATIMENT"],
                "par_defaut_pour": ["BATIMENT"],
                "est_actif": True,
            },
            format="json",
        )
        assert rep_a.status_code == 201
        id_a = rep_a.json()["id"]
        assert rep_a.json()["version"] == 1

        rep_b = client.post(
            "/api/v1/admins/decoupage/modeles/",
            {
                **_payload_modele("Voirie Urbaine"),
                "description": "Tracé routier",
                "types_projet": ["ROUTE"],
                "par_defaut_pour": [],
                "est_actif": False,
            },
            format="json",
        )
        assert rep_b.status_code == 201
        id_b = rep_b.json()["id"]

        # Filtres ?recherche=, ?type_projet=, ?est_actif=
        res_rech = client.get(
            "/api/v1/admins/decoupage/modeles/?recherche=residentiel eleve"
        ).json()
        assert [m["id"] for m in res_rech] == [id_a]

        res_type = client.get("/api/v1/admins/decoupage/modeles/?type_projet=ROUTE").json()
        assert [m["id"] for m in res_type] == [id_b]

        res_actif = client.get("/api/v1/admins/decoupage/modeles/?est_actif=true").json()
        assert id_a in [m["id"] for m in res_actif]
        assert id_b not in [m["id"] for m in res_actif]

        res_inactif = client.get("/api/v1/admins/decoupage/modeles/?est_actif=false").json()
        assert [m["id"] for m in res_inactif] == [id_b]

        # PATCH partiel sans niveaux/lignes : version reste 1
        rep_patch_meta = client.patch(
            f"/api/v1/admins/decoupage/modeles/{id_a}/",
            {"description": "Description révisée"},
            format="json",
        )
        assert rep_patch_meta.status_code == 200
        assert rep_patch_meta.json()["description"] == "Description révisée"
        assert rep_patch_meta.json()["version"] == 1
        assert rep_patch_meta.json()["niveaux_libelles"] == ["Phase", "Lot", "Activité"]
        assert rep_patch_meta.json()["nombre_lignes"] == 2

        # Actions rapides désactiver / activer : version reste 1
        rep_des = client.post(f"/api/v1/admins/decoupage/modeles/{id_a}/desactiver/")
        assert rep_des.status_code == 200
        assert rep_des.json()["est_actif"] is False
        assert rep_des.json()["version"] == 1

        rep_act = client.post(f"/api/v1/admins/decoupage/modeles/{id_a}/activer/")
        assert rep_act.status_code == 200
        assert rep_act.json()["est_actif"] is True
        assert rep_act.json()["version"] == 1

        # PUT avec gabarit identique (juste métadonnée changée) : version reste 1
        rep_put_identique = client.put(
            f"/api/v1/admins/decoupage/modeles/{id_a}/",
            {
                **_payload_modele("Résidentiel Élevé"),
                "description": "Toujours v1",
            },
            format="json",
        )
        assert rep_put_identique.status_code == 200
        assert rep_put_identique.json()["version"] == 1

        # PATCH avec changement réel des lignes : version passe à 2
        rep_patch_lignes = client.patch(
            f"/api/v1/admins/decoupage/modeles/{id_a}/",
            {
                "lignes": [
                    ["Fondations", "Gros œuvre", "Terrassement"],
                    ["Fondations", "Gros œuvre", "Semelles"],
                    ["Élévation", "Gros œuvre", "Poteaux"],
                ]
            },
            format="json",
        )
        assert rep_patch_lignes.status_code == 200
        assert rep_patch_lignes.json()["version"] == 2
        assert rep_patch_lignes.json()["nombre_lignes"] == 3

        # PATCH avec changement réel des niveaux : version passe à 3
        rep_patch_niveaux = client.patch(
            f"/api/v1/admins/decoupage/modeles/{id_a}/",
            {
                "niveaux": [
                    {"libelle": "Phase", "liste": None, "alerter": False},
                    {"libelle": "Lot", "liste": None, "alerter": False},
                    {"libelle": "Tâche", "liste": None, "alerter": True},
                ]
            },
            format="json",
        )
        assert rep_patch_niveaux.status_code == 200
        assert rep_patch_niveaux.json()["version"] == 3

    def test_dupliquer_modele_cree_copie_unique_v1_sans_defaut(
        self, superviseur, types_projet_plateforme
    ):
        client = _client_pour(superviseur)
        original = client.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Gabarit Base"),
            format="json",
        ).json()
        # Monter la version à 2 sur l'original
        client.patch(
            f"/api/v1/admins/decoupage/modeles/{original['id']}/",
            {"lignes": [["Phase 1", "Lot 1", "Tâche 1"]]},
            format="json",
        )

        copie1 = client.post(f"/api/v1/admins/decoupage/modeles/{original['id']}/dupliquer/")
        assert copie1.status_code == 201
        d1 = copie1.json()
        assert d1["id"] != original["id"]
        assert d1["nom"] == "Gabarit Base (copie)"
        assert d1["version"] == 1
        assert d1["est_actif"] is True
        assert d1["par_defaut_pour"] == []
        assert d1["types_projet"] == ["BATIMENT"]
        assert len(d1["niveaux"]) == 3
        assert len(d1["lignes"]) == 1

        copie2 = client.post(f"/api/v1/admins/decoupage/modeles/{original['id']}/dupliquer/")
        assert copie2.status_code == 201
        assert copie2.json()["nom"] == "Gabarit Base (copie 2)"

    def test_compteur_nombre_copies_entreprises_exact(self, superviseur, types_projet_plateforme):
        client_sup = _client_pour(superviseur)
        modele = client_sup.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle Compteur Copies"),
            format="json",
        ).json()
        modele_id = modele["id"]
        assert modele["nombre_copies_entreprises"] == 0

        _, dg_a = _creer_entreprise_et_dg("alpha")
        _, dg_b = _creer_entreprise_et_dg("beta")

        rep1 = _client_pour(dg_a).post(
            f"/api/v1/decoupage/modeles/plateforme/{modele_id}/personnaliser/"
        )
        assert rep1.status_code == 201

        detail_1 = client_sup.get(f"/api/v1/admins/decoupage/modeles/{modele_id}/").json()
        assert detail_1["nombre_copies_entreprises"] == 1

        rep2 = _client_pour(dg_b).post(
            f"/api/v1/decoupage/modeles/plateforme/{modele_id}/personnaliser/"
        )
        assert rep2.status_code == 201

        detail_2 = client_sup.get(f"/api/v1/admins/decoupage/modeles/{modele_id}/").json()
        assert detail_2["nombre_copies_entreprises"] == 2

        liste = client_sup.get("/api/v1/admins/decoupage/modeles/?recherche=Compteur Copies").json()
        assert liste[0]["nombre_copies_entreprises"] == 2

        # Suppression de la copie de B → compteur revient à 1
        copie_b_id = rep2.json()["id"]
        assert (
            _client_pour(dg_b)
            .delete(f"/api/v1/decoupage/modeles/ENTREPRISE/{copie_b_id}/")
            .status_code
            == 204
        )
        detail_3 = client_sup.get(f"/api/v1/admins/decoupage/modeles/{modele_id}/").json()
        assert detail_3["nombre_copies_entreprises"] == 1


# --------------------------------------------------------------------------
# 3. Non-régression import fichier CSV / XLSX (plus de FieldError sur est_actif)
# --------------------------------------------------------------------------
class TestImportFichierModelePlateforme:
    def test_import_csv_valide_retourne_200_et_lie_listes_actives(self, superviseur):
        client = _client_pour(superviseur)
        liste_active = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Phases Import", "valeurs": ["Préparation"]},
            format="json",
        ).json()
        liste_inactive = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Lots Import", "valeurs": ["Gros œuvre"]},
            format="json",
        ).json()
        client.post(f"/api/v1/admins/decoupage/listes/{liste_inactive['id']}/desactiver/")

        contenu_csv = (
            "Phases Import;Lots Import;Activité\n"
            "Préparation;Gros œuvre;Installation\n"
            "Exécution;Gros œuvre;Fouilles\n"
        ).encode()
        fichier = SimpleUploadedFile("gabarit.csv", contenu_csv, content_type="text/csv")

        rep = client.post(
            "/api/v1/admins/decoupage/modeles/importer-fichier/",
            {"fichier": fichier},
            format="multipart",
        )
        assert rep.status_code == 200, rep.content
        donnees = rep.json()
        assert len(donnees["niveaux"]) == 3
        assert donnees["niveaux"][0]["liste"]["id"] == liste_active["id"]
        # Une liste désactivée n'est pas proposée aux nouvelles liaisons
        assert donnees["niveaux"][1]["liste"] is None
        assert len(donnees["lignes"]) == 2

    def test_import_xlsx_valide_retourne_200(self, superviseur):
        client = _client_pour(superviseur)
        wb = Workbook()
        ws = wb.active
        ws.append(["Phase", "Ouvrage", "Tâche"])
        ws.append(["Gros œuvre", "Fondations", "Semelles filantes"])
        ws.append(["Second œuvre", "Électricité", "Câblage"])
        tampon = io.BytesIO()
        wb.save(tampon)

        fichier = SimpleUploadedFile(
            "gabarit.xlsx",
            tampon.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        rep = client.post(
            "/api/v1/admins/decoupage/modeles/importer-fichier/",
            {"fichier": fichier},
            format="multipart",
        )
        assert rep.status_code == 200, rep.content
        donnees = rep.json()
        assert [n["libelle"] for n in donnees["niveaux"]] == ["Phase", "Ouvrage", "Tâche"]
        assert len(donnees["lignes"]) == 2


# --------------------------------------------------------------------------
# 4. Listes plateforme : est_actif, compteurs & protection cross-tenant DELETE
# --------------------------------------------------------------------------
class TestListesPlateformeEtProtectionCrossTenant:
    def test_est_actif_et_compteurs_utilisations(self, superviseur, types_projet_plateforme):
        client = _client_pour(superviseur)
        liste = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Corps État QA", "valeurs": ["Maçonnerie", "Peinture"]},
            format="json",
        ).json()
        liste_id = liste["id"]
        assert liste["est_actif"] is True
        assert liste["nombre_utilisations_plateforme"] == 0
        assert liste["nombre_utilisations_entreprises"] == 0

        # Usage par un modèle plateforme
        client.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle Avec Liste QA", liste_id=liste_id),
            format="json",
        )

        # Usage par un modèle entreprise + un projet entreprise
        ent, dg = _creer_entreprise_et_dg("usages")
        with contexte_entreprise(ent):
            mod_ent = ModeleDecoupageEntreprise.objects.create(
                nom="Modèle Ent Liste QA",
                types_projet=["BATIMENT"],
                cree_par=dg,
            )
            NiveauModeleEntreprise.objects.create(
                modele=mod_ent,
                ordre=1,
                libelle="Lot",
                liste_plateforme_id=liste_id,
            )
            projet = Projet.objects.create(
                reference=f"PRJ-{uuid.uuid4().hex[:5].upper()}",
                nom="Chantier Liste QA",
                ville="Abidjan",
                quartier="Cocody",
                statut=StatutProjet.EN_COURS,
            )
            NiveauProjet.objects.create(
                projet=projet,
                ordre=1,
                libelle="Lot",
                liste_plateforme_id=liste_id,
            )

        detail = client.get(f"/api/v1/admins/decoupage/listes/{liste_id}/").json()
        assert detail["nombre_utilisations_plateforme"] == 1
        assert detail["nombre_utilisations_entreprises"] == 2

        # PATCH est_actif=False, puis activer / desactiver
        rep_patch = client.patch(
            f"/api/v1/admins/decoupage/listes/{liste_id}/",
            {"est_actif": False},
            format="json",
        )
        assert rep_patch.status_code == 200
        assert rep_patch.json()["est_actif"] is False

        assert (
            client.get("/api/v1/admins/decoupage/listes/?est_actif=false").json()[0]["id"]
            == liste_id
        )
        assert (
            client.post(f"/api/v1/admins/decoupage/listes/{liste_id}/activer/").json()["est_actif"]
            is True
        )
        assert (
            client.post(f"/api/v1/admins/decoupage/listes/{liste_id}/desactiver/").json()[
                "est_actif"
            ]
            is False
        )

    def test_delete_liste_bloquee_422_si_niveau_modele_entreprise_seul(self, superviseur):
        client = _client_pour(superviseur)
        liste_id = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Liste Ent Seule", "valeurs": ["V1"]},
            format="json",
        ).json()["id"]

        ent, dg = _creer_entreprise_et_dg("modent")
        with contexte_entreprise(ent):
            mod_ent = ModeleDecoupageEntreprise.objects.create(
                nom="Modèle Entreprise Référent",
                cree_par=dg,
            )
            NiveauModeleEntreprise.objects.create(
                modele=mod_ent,
                ordre=1,
                libelle="Phase",
                liste_plateforme_id=liste_id,
            )

        # Suppression refusée en 422 même si aucun modèle plateforme ne la cite
        rep_del = client.delete(f"/api/v1/admins/decoupage/listes/{liste_id}/")
        assert rep_del.status_code == 422, rep_del.content
        details = rep_del.json()["erreur"]["details"]
        assert details.get("usages_plateforme") == 0
        assert details.get("usages_modeles_entreprise") == 1
        assert details.get("usages_projets") == 0

        # La désactivation réussit et ne casse ni la lecture ni la modification du modèle entreprise
        rep_des = client.post(f"/api/v1/admins/decoupage/listes/{liste_id}/desactiver/")
        assert rep_des.status_code == 200
        assert rep_des.json()["est_actif"] is False

        client_ent = _client_pour(dg)
        rep_lecture = client_ent.get(f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_ent.pk}/")
        assert rep_lecture.status_code == 200
        rep_modif = client_ent.patch(
            f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_ent.pk}/",
            {"description": "Toujours éditable malgré liste désactivée"},
            format="json",
        )
        assert rep_modif.status_code == 200

        # Une fois le modèle entreprise supprimé, DELETE sur la liste passe en 204
        assert (
            client_ent.delete(f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_ent.pk}/").status_code
            == 204
        )
        assert client.delete(f"/api/v1/admins/decoupage/listes/{liste_id}/").status_code == 204

    def test_delete_liste_bloquee_422_si_niveau_projet_seul(self, superviseur):
        client = _client_pour(superviseur)
        liste_id = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Liste Projet Seul", "valeurs": ["V1"]},
            format="json",
        ).json()["id"]

        ent, _ = _creer_entreprise_et_dg("proj")
        with contexte_entreprise(ent):
            projet = Projet.objects.create(
                reference=f"PRJ-{uuid.uuid4().hex[:5].upper()}",
                nom="Projet Référent",
                ville="Abidjan",
                quartier="Marcory",
                statut=StatutProjet.EN_COURS,
            )
            NiveauProjet.objects.create(
                projet=projet,
                ordre=1,
                libelle="Lot",
                liste_plateforme_id=liste_id,
            )

        rep_del = client.delete(f"/api/v1/admins/decoupage/listes/{liste_id}/")
        assert rep_del.status_code == 422
        details = rep_del.json()["erreur"]["details"]
        assert details.get("usages_projets") == 1


# --------------------------------------------------------------------------
# 5. Journalisation JournalPlateforme
# --------------------------------------------------------------------------
class TestJournalisationDecoupagePlateforme:
    def test_actions_decoupage_journalisees_dans_journal_plateforme(
        self, superviseur, types_projet_plateforme
    ):
        client = _client_pour(superviseur)

        # Listes & valeurs
        liste = client.post(
            "/api/v1/admins/decoupage/listes/",
            {"libelle": "Liste Audit QA", "valeurs": ["Val 1"]},
            format="json",
        ).json()
        liste_id = liste["id"]
        val_id = liste["valeurs"][0]["id"]

        client.patch(
            f"/api/v1/admins/decoupage/listes/{liste_id}/",
            {"description": "Maj audit"},
            format="json",
        )
        client.post(f"/api/v1/admins/decoupage/listes/{liste_id}/desactiver/")
        client.post(f"/api/v1/admins/decoupage/listes/{liste_id}/activer/")
        client.post(
            f"/api/v1/admins/decoupage/listes/{liste_id}/valeurs/",
            {"valeurs": ["Val 2"]},
            format="json",
        )
        client.patch(
            f"/api/v1/admins/decoupage/valeurs/{val_id}/",
            {"libelle": "Val 1 bis"},
            format="json",
        )
        client.delete(f"/api/v1/admins/decoupage/valeurs/{val_id}/")
        client.delete(f"/api/v1/admins/decoupage/listes/{liste_id}/")

        # Modèles
        modele_id = client.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle Audit QA"),
            format="json",
        ).json()["id"]
        client.patch(
            f"/api/v1/admins/decoupage/modeles/{modele_id}/",
            {"description": "Maj"},
            format="json",
        )
        client.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/desactiver/")
        client.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/activer/")
        dup_id = client.post(f"/api/v1/admins/decoupage/modeles/{modele_id}/dupliquer/").json()[
            "id"
        ]
        client.delete(f"/api/v1/admins/decoupage/modeles/{dup_id}/")
        client.delete(f"/api/v1/admins/decoupage/modeles/{modele_id}/")

        actions = set(
            JournalPlateforme.objects.filter(utilisateur_id=superviseur.pk).values_list(
                "action", flat=True
            )
        )
        attendues = {
            "DECOUPAGE_LISTE_CREATION",
            "DECOUPAGE_LISTE_MODIFICATION",
            "DECOUPAGE_LISTE_DESACTIVATION",
            "DECOUPAGE_LISTE_ACTIVATION",
            "DECOUPAGE_LISTE_RETRAIT",
            "DECOUPAGE_VALEURS_AJOUT",
            "DECOUPAGE_VALEUR_MODIFICATION",
            "DECOUPAGE_VALEUR_RETRAIT",
            "DECOUPAGE_MODELE_CREATION",
            "DECOUPAGE_MODELE_MODIFICATION",
            "DECOUPAGE_MODELE_DESACTIVATION",
            "DECOUPAGE_MODELE_ACTIVATION",
            "DECOUPAGE_MODELE_DUPLICATION",
            "DECOUPAGE_MODELE_RETRAIT",
        }
        assert attendues.issubset(actions)


# --------------------------------------------------------------------------
# 6. Commande idempotente synchroniser_catalogue_decoupage
# --------------------------------------------------------------------------
class TestCommandeSynchroniserCatalogueDecoupage:
    def test_idempotente_avec_entreprises_et_respecte_modifs_super_admin(self, superviseur):
        # S'assurer qu'au moins une entreprise existe en base
        _creer_entreprise_et_dg("sync")
        assert Entreprise.objects.exists()

        # 1re passe : synchronise les éléments de fixture manquants
        call_command("synchroniser_catalogue_decoupage", stdout=io.StringIO())
        nb_listes = ListeValeursPlateforme._base_manager.count()
        nb_valeurs = ValeurListePlateforme._base_manager.count()
        nb_modeles = ModeleDecoupagePlateforme._base_manager.count()
        nb_niveaux = NiveauModelePlateforme._base_manager.count()
        nb_lignes = LigneModelePlateforme._base_manager.count()
        assert nb_listes > 0
        assert nb_modeles > 0

        # Modifier un modèle et en désactiver/supprimer un autre côté Super Admin
        modele_modifie = ModeleDecoupagePlateforme.objects.order_by("nom").first()
        assert modele_modifie is not None
        modele_modifie.description = "Personnalisation Super Admin à préserver"
        modele_modifie.est_actif = False
        modele_modifie.version = 7
        modele_modifie.save()

        modele_supprime = ModeleDecoupagePlateforme.objects.exclude(pk=modele_modifie.pk).first()
        assert modele_supprime is not None
        modele_supprime.delete(utilisateur=superviseur)

        # 2e passe : ne duplique rien, n'écrase pas la notif Super Admin, ne ressuscite pas
        sortie = io.StringIO()
        call_command("synchroniser_catalogue_decoupage", stdout=sortie)
        assert "Listes insérées : 0" in sortie.getvalue()
        assert "Modèles insérés : 0" in sortie.getvalue()

        assert ListeValeursPlateforme._base_manager.count() == nb_listes
        assert ValeurListePlateforme._base_manager.count() == nb_valeurs
        assert ModeleDecoupagePlateforme._base_manager.count() == nb_modeles
        assert NiveauModelePlateforme._base_manager.count() == nb_niveaux
        assert LigneModelePlateforme._base_manager.count() == nb_lignes

        modele_modifie.refresh_from_db()
        assert modele_modifie.description == "Personnalisation Super Admin à préserver"
        assert modele_modifie.est_actif is False
        assert modele_modifie.version == 7

        # Le modèle supprimé logiquement reste supprimé
        assert not ModeleDecoupagePlateforme.objects.filter(pk=modele_supprime.pk).exists()
        assert (
            ModeleDecoupagePlateforme._base_manager.get(pk=modele_supprime.pk).supprime_le
            is not None
        )
