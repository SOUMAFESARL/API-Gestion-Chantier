"""Tests des modèles et listes de découpage côté Entreprise (source unique, priorité, dérive)."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.authentification import emettre_jetons
from apps.catalogue.models import (
    CategorieReferentiel,
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    ReferentielPlateforme,
    ValeurListePlateforme,
)
from apps.core.contexte import contexte_entreprise, portee_plateforme, reinitialiser_contexte
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutProjet, StatutUtilisateur
from apps.entreprises.models import Entreprise
from apps.projets.models import (
    LigneModeleEntreprise,
    ModeleDecoupageEntreprise,
    NiveauModeleEntreprise,
    Projet,
)
from apps.projets.services import listes_modeles as lm

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


def _creer_entreprise_et_dg(prefixe: str) -> tuple[Entreprise, Utilisateur]:
    slug = f"{prefixe}-{uuid.uuid4().hex[:6]}"
    ent = Entreprise.objects.create(
        slug=slug,
        raison_sociale=f"Entreprise {slug}",
        email_contact=f"contact@{slug}.ci",
        statut=StatutEntreprise.ACTIF,
    )
    with contexte_entreprise(ent):
        dg = Utilisateur.objects.create_user(
            email=f"dg@{slug}.ci",
            password="TestPassword123!",
            nom="Directeur",
            prenom=prefixe.capitalize(),
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        dg.is_owner = True
        dg.save(update_fields=["is_owner", "modifie_le"])
    return ent, dg


@pytest.fixture
def types_projet():
    crees = {}
    for ordre, (code, libelle) in enumerate(
        [("BATIMENT", "Bâtiment"), ("ROUTE", "Route")], start=1
    ):
        obj, _ = ReferentielPlateforme.objects.get_or_create(
            categorie=CategorieReferentiel.TYPE_PROJET,
            code=code,
            defaults={"libelle": libelle, "ordre": ordre},
        )
        crees[code] = obj
    return crees


@pytest.fixture
def super_admin() -> Utilisateur:
    return Utilisateur.objects.create_superuser(
        email=f"sa-{uuid.uuid4().hex[:8]}@ccd-plateforme.ci",
        password="TestPassword123!",
        nom="Super",
        prenom="Admin",
    )


def _payload_modele(
    nom: str,
    *,
    types_projet: list[str] | None = None,
    par_defaut_pour: list[str] | None = None,
) -> dict:
    return {
        "nom": nom,
        "description": "Description initiale",
        "types_projet": types_projet if types_projet is not None else ["BATIMENT"],
        "par_defaut_pour": par_defaut_pour if par_defaut_pour is not None else [],
        "niveaux": [
            {"libelle": "Phase", "liste": None, "alerter": False},
            {"libelle": "Lot", "liste": None, "alerter": True},
            {"libelle": "Activité", "liste": None, "alerter": False},
        ],
        "lignes": [
            ["Fondations", "Gros œuvre", "Terrassement"],
            ["Fondations", "Gros œuvre", "Béton de propreté"],
        ],
    }


# --------------------------------------------------------------------------
# 1. Source unique sans copie & visibilité immédiate / désactivation
# --------------------------------------------------------------------------
class TestSourceUniqueSansCopie:
    def test_modele_plateforme_visible_immediatement_sans_copie_et_disparait_si_desactive(
        self, super_admin, types_projet
    ):
        _ent_a, dg_a = _creer_entreprise_et_dg("src-a")
        _ent_b, dg_b = _creer_entreprise_et_dg("src-b")
        client_sa = _client_pour(super_admin)
        client_a = _client_pour(dg_a)
        client_b = _client_pour(dg_b)

        with portee_plateforme(motif="vérifier absence de copie initiale"):
            copies_avant = ModeleDecoupageEntreprise.objects.count()

        # Super Admin crée un modèle plateforme
        rep_creation = client_sa.post(
            "/api/v1/admins/decoupage/modeles/",
            {
                **_payload_modele("Modèle Global Source Unique", par_defaut_pour=["BATIMENT"]),
                "est_actif": True,
            },
            format="json",
        )
        assert rep_creation.status_code == 201
        plat_id = rep_creation.json()["id"]

        # Aucune copie créée dans ModeleDecoupageEntreprise
        with portee_plateforme(motif="vérifier zéro duplication"):
            assert ModeleDecoupageEntreprise.objects.count() == copies_avant

        # Visible immédiatement pour A et B
        ids_a = [m["id"] for m in client_a.get("/api/v1/decoupage/modeles/").json()]
        ids_b = [m["id"] for m in client_b.get("/api/v1/decoupage/modeles/").json()]
        assert plat_id in ids_a
        assert plat_id in ids_b

        # Modification côté Super Admin répercutée immédiatement sans copie
        client_sa.patch(
            f"/api/v1/admins/decoupage/modeles/{plat_id}/",
            {"nom": "Modèle Global Mis À Jour"},
            format="json",
        )
        detail_a = client_a.get(f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/")
        detail_b = client_b.get(f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/")
        assert detail_a.status_code == 200
        assert detail_b.status_code == 200
        assert detail_a.json()["nom"] == "Modèle Global Mis À Jour"
        assert detail_b.json()["nom"] == "Modèle Global Mis À Jour"

        # Désactivation : disparaît immédiatement côté entreprises
        assert (
            client_sa.post(f"/api/v1/admins/decoupage/modeles/{plat_id}/desactiver/").status_code
            == 200
        )
        assert plat_id not in [m["id"] for m in client_a.get("/api/v1/decoupage/modeles/").json()]
        assert plat_id not in [m["id"] for m in client_b.get("/api/v1/decoupage/modeles/").json()]
        assert client_a.get(f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/").status_code == 404


# --------------------------------------------------------------------------
# 2. Règle de priorité modele_par_defaut (décision PO)
# --------------------------------------------------------------------------
class TestPrioriteModeleParDefaut:
    def test_priorite_plateforme_vs_entreprise_selon_par_defaut_pour(
        self, super_admin, types_projet
    ):
        client_sa = _client_pour(super_admin)

        # Nettoyer les défauts éventuels sur BATIMENT et ROUTE pour isoler le test
        for existant in ModeleDecoupagePlateforme.objects.all():
            restants = [
                t for t in (existant.par_defaut_pour or []) if t not in ("BATIMENT", "ROUTE")
            ]
            if restants != list(existant.par_defaut_pour or []):
                existant.par_defaut_pour = restants
                existant.save(update_fields=["par_defaut_pour", "modifie_le"])

        plat_bat = client_sa.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele(
                "Plateforme Bâtiment Défaut",
                types_projet=["BATIMENT"],
                par_defaut_pour=["BATIMENT"],
            ),
            format="json",
        ).json()
        plat_route = client_sa.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele(
                "Plateforme Route Défaut",
                types_projet=["ROUTE"],
                par_defaut_pour=["ROUTE"],
            ),
            format="json",
        ).json()

        ent, dg = _creer_entreprise_et_dg("prio")
        client_ent = _client_pour(dg)

        # 1) L'entreprise crée un modèle pour BATIMENT SANS cocher par_defaut_pour
        mod_ent = client_ent.post(
            "/api/v1/decoupage/modeles/",
            _payload_modele(
                "Entreprise Bâtiment Non Défaut",
                types_projet=["BATIMENT"],
                par_defaut_pour=[],
            ),
            format="json",
        )
        assert mod_ent.status_code == 201
        mod_ent_id = mod_ent.json()["id"]

        liste_bat = client_ent.get("/api/v1/decoupage/modeles/?type_projet=BATIMENT").json()
        defauts_bat = [m for m in liste_bat if m["par_defaut"]]
        assert len(defauts_bat) == 1
        assert defauts_bat[0]["id"] == plat_bat["id"]
        assert defauts_bat[0]["origine"] == "PLATEFORME"

        with contexte_entreprise(ent):
            assert str(lm.modele_par_defaut("BATIMENT").pk) == plat_bat["id"]

        # 2) L'entreprise coche explicitement par_defaut_pour=["BATIMENT"] sur son modèle
        rep_patch = client_ent.patch(
            f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_ent_id}/",
            {"par_defaut_pour": ["BATIMENT"]},
            format="json",
        )
        assert rep_patch.status_code == 200

        liste_bat_apres = client_ent.get("/api/v1/decoupage/modeles/?type_projet=BATIMENT").json()
        defauts_bat_apres = [m for m in liste_bat_apres if m["par_defaut"]]
        assert len(defauts_bat_apres) == 1
        assert defauts_bat_apres[0]["id"] == mod_ent_id
        assert defauts_bat_apres[0]["origine"] == "ENTREPRISE"

        # Pour ROUTE, le modèle plateforme reste prioritaire !
        liste_route = client_ent.get("/api/v1/decoupage/modeles/?type_projet=ROUTE").json()
        defauts_route = [m for m in liste_route if m["par_defaut"]]
        assert len(defauts_route) == 1
        assert defauts_route[0]["id"] == plat_route["id"]
        assert defauts_route[0]["origine"] == "PLATEFORME"

        with contexte_entreprise(ent):
            assert str(lm.modele_par_defaut("BATIMENT").pk) == mod_ent_id
            assert str(lm.modele_par_defaut("ROUTE").pk) == plat_route["id"]


# --------------------------------------------------------------------------
# 3. Personnalisation & dérive (original_modifie / original_supprime)
# --------------------------------------------------------------------------
class TestPersonnalisationEtDerive:
    def test_personnalisation_casse_minuscule_et_cycle_derive(self, super_admin, types_projet):
        client_sa = _client_pour(super_admin)
        plat = client_sa.post(
            "/api/v1/admins/decoupage/modeles/",
            _payload_modele("Modèle À Personnaliser", types_projet=["BATIMENT"]),
            format="json",
        ).json()
        plat_id = plat["id"]

        ent, dg = _creer_entreprise_et_dg("perso")
        client_ent = _client_pour(dg)

        # Casse minuscule `/plateforme/{id}/personnaliser/`
        rep_perso = client_ent.post(
            f"/api/v1/decoupage/modeles/plateforme/{plat_id}/personnaliser/"
        )
        assert rep_perso.status_code == 201, rep_perso.content
        copie = rep_perso.json()
        copie_id = copie["id"]
        assert copie["origine"] == "ENTREPRISE"
        assert copie["est_personnalise"] is True
        assert copie["origine_plateforme_id"] == plat_id
        assert copie["original_modifie"] is False
        assert copie["original_supprime"] is False

        # 2e personnalisation refusée en 422
        rep_doublon = client_ent.post(
            f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/personnaliser/"
        )
        assert rep_doublon.status_code == 422

        # Modification non-structurelle (description) → original_modifie reste False
        client_sa.patch(
            f"/api/v1/admins/decoupage/modeles/{plat_id}/",
            {"description": "Nouvelle description sans changer le gabarit"},
            format="json",
        )
        etat_1 = client_ent.get(f"/api/v1/decoupage/modeles/ENTREPRISE/{copie_id}/").json()
        assert etat_1["original_modifie"] is False

        # Désactivation (est_actif=False) : version inchangée, original_modifie reste False
        client_sa.post(f"/api/v1/admins/decoupage/modeles/{plat_id}/desactiver/")
        etat_desact = client_ent.get(f"/api/v1/decoupage/modeles/ENTREPRISE/{copie_id}/").json()
        assert etat_desact["original_modifie"] is False
        client_sa.post(f"/api/v1/admins/decoupage/modeles/{plat_id}/activer/")

        # Modification structurelle (ajout d'une ligne) → original_modifie devient True
        client_sa.patch(
            f"/api/v1/admins/decoupage/modeles/{plat_id}/",
            {
                "lignes": [
                    ["Fondations", "Gros œuvre", "Terrassement"],
                    ["Fondations", "Gros œuvre", "Béton de propreté"],
                    ["Superstructure", "Gros œuvre", "Dalle"],
                ]
            },
            format="json",
        )
        etat_2 = client_ent.get(f"/api/v1/decoupage/modeles/ENTREPRISE/{copie_id}/").json()
        assert etat_2["original_modifie"] is True
        assert etat_2["origine_plateforme_id"] == plat_id

        # Soft-delete du modèle plateforme → origine_plateforme_id=None, original_supprime=True
        assert client_sa.delete(f"/api/v1/admins/decoupage/modeles/{plat_id}/").status_code == 204
        etat_3 = client_ent.get(f"/api/v1/decoupage/modeles/ENTREPRISE/{copie_id}/").json()
        assert etat_3["origine_plateforme_id"] is None
        assert etat_3["original_supprime"] is True
        assert etat_3["est_personnalise"] is True

        # La copie reste utilisable (lecture, PATCH et proposition de tableau projet)
        assert (
            client_ent.patch(
                f"/api/v1/decoupage/modeles/ENTREPRISE/{copie_id}/",
                {"description": "Copie autonome utilisable"},
                format="json",
            ).status_code
            == 200
        )
        with contexte_entreprise(ent):
            projet = Projet.objects.create(
                reference=f"PRJ-{uuid.uuid4().hex[:5].upper()}",
                nom="Projet Copie Autonome",
                ville="Abidjan",
                quartier="Plateau",
                statut=StatutProjet.EN_COURS,
            )
        rep_prop = client_ent.get(
            f"/api/v1/projets/{projet.pk}/decoupage/?modele_origine=ENTREPRISE&modele_id={copie_id}"
        )
        assert rep_prop.status_code == 200
        assert len(rep_prop.json()["lignes"]) == 2


# --------------------------------------------------------------------------
# 4. Protections, validations, soft-delete cascadé & étanchéité A vs B
# --------------------------------------------------------------------------
class TestProtectionsValidationsEtEtancheite:
    def test_ecriture_entreprise_sur_modele_plateforme_refusee_422(self, super_admin, types_projet):
        plat = (
            _client_pour(super_admin)
            .post(
                "/api/v1/admins/decoupage/modeles/",
                _payload_modele("Modèle Plateforme Protégé"),
                format="json",
            )
            .json()
        )
        plat_id = plat["id"]

        _, dg = _creer_entreprise_et_dg("prot")
        client_ent = _client_pour(dg)

        assert (
            client_ent.put(
                f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/",
                _payload_modele("Hack"),
                format="json",
            ).status_code
            == 422
        )
        assert (
            client_ent.patch(
                f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/",
                {"nom": "Hack"},
                format="json",
            ).status_code
            == 422
        )
        assert (
            client_ent.delete(f"/api/v1/decoupage/modeles/PLATEFORME/{plat_id}/").status_code == 422
        )

    def test_patch_partiel_validation_par_defaut_et_soft_delete_cascade(self, types_projet):
        ent, dg = _creer_entreprise_et_dg("crud-ent")
        client = _client_pour(dg)

        # Validation par_defaut_pour ⊆ types_projet (400)
        rep_invalide = client.post(
            "/api/v1/decoupage/modeles/",
            _payload_modele(
                "Modèle Invalide",
                types_projet=["BATIMENT"],
                par_defaut_pour=["ROUTE"],
            ),
            format="json",
        )
        assert rep_invalide.status_code == 400
        assert "par_defaut_pour" in rep_invalide.json()["erreur"]["details"]

        # Création valide
        rep = client.post(
            "/api/v1/decoupage/modeles/",
            _payload_modele("Modèle Ent Partiel", types_projet=["BATIMENT"]),
            format="json",
        )
        assert rep.status_code == 201
        mod_id = rep.json()["id"]

        # PATCH validation par_defaut_pour ⊆ types_projet (400)
        rep_patch_inv = client.patch(
            f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_id}/",
            {"par_defaut_pour": ["ROUTE"]},
            format="json",
        )
        assert rep_patch_inv.status_code == 400

        # PATCH partiel sans niveaux/lignes conserve les niveaux et lignes
        rep_patch = client.patch(
            f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_id}/",
            {"description": "Description patchée"},
            format="json",
        )
        assert rep_patch.status_code == 200
        donnees = rep_patch.json()
        assert donnees["description"] == "Description patchée"
        assert [n["libelle"] for n in donnees["niveaux"]] == ["Phase", "Lot", "Activité"]
        assert len(donnees["lignes"]) == 2

        # Soft-delete cascadé des niveaux et lignes
        assert client.delete(f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_id}/").status_code == 204
        with contexte_entreprise(ent):
            assert NiveauModeleEntreprise.objects.filter(modele_id=mod_id).count() == 0
            assert LigneModeleEntreprise.objects.filter(modele_id=mod_id).count() == 0
            niveaux_suppr = list(NiveauModeleEntreprise.tous_objets.filter(modele_id=mod_id))
            lignes_suppr = list(LigneModeleEntreprise.tous_objets.filter(modele_id=mod_id))
            assert len(niveaux_suppr) == 3
            assert len(lignes_suppr) == 2
            assert all(n.supprime_le is not None for n in niveaux_suppr)
            assert all(lg.supprime_le is not None for lg in lignes_suppr)

    def test_etancheite_stricte_entre_entreprise_a_et_b(self, types_projet):
        _, dg_a = _creer_entreprise_et_dg("iso-a")
        _, dg_b = _creer_entreprise_et_dg("iso-b")
        client_a = _client_pour(dg_a)
        client_b = _client_pour(dg_b)

        liste_a = client_a.post(
            "/api/v1/decoupage/listes/",
            {"libelle": "Liste Privée A", "valeurs": ["Secret A"]},
            format="json",
        ).json()
        mod_a = client_a.post(
            "/api/v1/decoupage/modeles/",
            _payload_modele("Modèle Privé A"),
            format="json",
        ).json()

        # B ne voit ni la liste ni le modèle de A dans les listings
        assert liste_a["id"] not in [
            lst["id"] for lst in client_b.get("/api/v1/decoupage/listes/").json()
        ]
        assert mod_a["id"] not in [
            m["id"] for m in client_b.get("/api/v1/decoupage/modeles/").json()
        ]

        # B reçoit 404 sur les ressources de A
        assert (
            client_b.get(f"/api/v1/decoupage/listes/ENTREPRISE/{liste_a['id']}/").status_code == 404
        )
        assert (
            client_b.patch(
                f"/api/v1/decoupage/listes/ENTREPRISE/{liste_a['id']}/",
                {"libelle": "X"},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_b.delete(f"/api/v1/decoupage/listes/ENTREPRISE/{liste_a['id']}/").status_code
            == 404
        )

        assert (
            client_b.get(f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_a['id']}/").status_code == 404
        )
        assert (
            client_b.patch(
                f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_a['id']}/", {"nom": "X"}, format="json"
            ).status_code
            == 404
        )
        assert (
            client_b.delete(f"/api/v1/decoupage/modeles/ENTREPRISE/{mod_a['id']}/").status_code
            == 404
        )


# --------------------------------------------------------------------------
# 5. Super Admin sur GET /api/v1/decoupage/listes/ (non-régression 500 HorsContexte)
# --------------------------------------------------------------------------
class TestSuperAdminSurRoutesDecoupage:
    def test_get_decoupage_listes_avec_jeton_super_admin_retourne_200(self, super_admin):
        liste_plat = ListeValeursPlateforme.objects.create(libelle="Phases SA Check")
        ValeurListePlateforme.objects.create(liste=liste_plat, libelle="Préparation", ordre=1)

        client_sa = _client_pour(super_admin)
        rep = client_sa.get("/api/v1/decoupage/listes/")
        assert rep.status_code == 200, rep.content
        donnees = rep.json()
        assert any(item["id"] == str(liste_plat.pk) for item in donnees)
        assert all(item["origine"] == "PLATEFORME" for item in donnees)

        rep_sans_val = client_sa.get("/api/v1/decoupage/listes/?valeurs=false")
        assert rep_sans_val.status_code == 200
        entree = next(item for item in rep_sans_val.json() if item["id"] == str(liste_plat.pk))
        assert entree["nombre_valeurs"] == 1
