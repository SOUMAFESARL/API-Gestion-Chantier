"""Retours du 22/10/2026 (B4) : chef de projet protégé, lot du chef de chantier, équipes.

Le chef de projet ne se retire, ne se désactive, ne se remplace et ne se nomme que par le DG ou
un rôle de portée entreprise qui affecte les membres. Un chef de chantier peut être rattaché à un
lot du projet. Un collaborateur peut appartenir à plusieurs équipes d'un même projet.
"""

from datetime import date

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import PERMISSIONS_DEFAUT_ROLES, initialiser_roles_par_defaut
from apps.chantier.selectors.journal import contexte_projet
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Lot, Projet

SCHEMA = "demo"
HOTE = "demo.localhost"
MESSAGE_PROTEGE = "Seule la direction peut retirer ou remplacer le chef de projet."

pytestmark = pytest.mark.django_db


def _utilisateur(email, nom, role):
    u, _ = Utilisateur.tous_objets.get_or_create(
        email=email,
        defaults={
            "nom": nom,
            "prenom": "Test",
            "role_global": role,
            "statut": StatutUtilisateur.ACTIF,
        },
    )
    return u


def _projet(reference, **champs):
    return Projet.objects.create(
        reference=reference,
        nom=f"Chantier {reference}",
        ville="Abidjan",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2027, 12, 31),
        statut=StatutProjet.EN_COURS,
        **champs,
    )


def _affecter(projet, utilisateur, role, **champs):
    return AffectationProjet.objects.create(
        projet=projet,
        utilisateur=utilisateur,
        role_projet=role,
        est_actif=True,
        date_debut=date(2026, 1, 1),
        **champs,
    )


def _client_pour(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _erreur(rep):
    return rep.json()["erreur"]


@pytest.fixture
def env(db):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        dg = _utilisateur("dg.b4r@demo.ci", "Directeur", RoleGlobal.DIRECTEUR_GENERAL)
        dg.is_owner = True
        dg.save(update_fields=["is_owner"])

        ad = _utilisateur("ad.b4r@demo.ci", "Admin", RoleGlobal.ADMIN)
        cp1 = _utilisateur("cp1.b4r@demo.ci", "CP Un", RoleGlobal.CHEF_PROJET)
        cp2 = _utilisateur("cp2.b4r@demo.ci", "CP Deux", RoleGlobal.CHEF_PROJET)
        cp3 = _utilisateur("cp3.b4r@demo.ci", "CP Trois", RoleGlobal.CHEF_PROJET)
        ct1 = _utilisateur("ct1.b4r@demo.ci", "CT Un", RoleGlobal.CONDUCTEUR_TRAVAUX)
        ct2 = _utilisateur("ct2.b4r@demo.ci", "CT Deux", RoleGlobal.CONDUCTEUR_TRAVAUX)
        cc1 = _utilisateur("cc1.b4r@demo.ci", "CC Un", RoleGlobal.CHEF_CHANTIER)
        cc2 = _utilisateur("cc2.b4r@demo.ci", "CC Deux", RoleGlobal.CHEF_CHANTIER)
        vi = _utilisateur("vi.b4r@demo.ci", "Visiteur", RoleGlobal.VISITEUR)

        projet1 = _projet("PRJ-B4R-01", chef_projet=cp1, conducteur_travaux=ct1)
        aff_cp1 = _affecter(projet1, cp1, RoleProjet.CHEF_PROJET)
        _affecter(projet1, ct1, RoleProjet.CONDUCTEUR_TRAVAUX)

        projet2 = _projet("PRJ-B4R-02", chef_projet=cp2)
        _affecter(projet2, cp2, RoleProjet.CHEF_PROJET)

        lot1 = Lot.objects.create(projet=projet1, code="L01", libelle="Gros œuvre")
        lot2 = Lot.objects.create(projet=projet1, code="L02", libelle="Électricité")
        lot_autre = Lot.objects.create(projet=projet2, code="L01", libelle="Lot d'un autre projet")

        return {
            "dg": dg,
            "ad": ad,
            "cp1": cp1,
            "cp2": cp2,
            "cp3": cp3,
            "ct1": ct1,
            "ct2": ct2,
            "cc1": cc1,
            "cc2": cc2,
            "vi": vi,
            "projet1": projet1,
            "projet2": projet2,
            "aff_cp1": aff_cp1,
            "lot1": lot1,
            "lot2": lot2,
            "lot_autre": lot_autre,
        }


def _affecter_en_renfort(projet, utilisateur):
    """Un titulaire du rôle CP affecté au chantier sans y être son chef de projet.

    Il détient `projets.affecter_membres` mais n'est pas de portée entreprise : l'affectation
    porte le rôle CT pour ne pas ajouter un second chef de projet actif au chantier.
    """
    return _affecter(projet, utilisateur, RoleProjet.CONDUCTEUR_TRAVAUX)


def _url(projet, suite=""):
    return f"/api/v1/projets/{projet.id}/affectations/{suite}"


# --------------------------------------------------------------------------
# (1) Le chef de projet est protégé
# --------------------------------------------------------------------------
def test_ct_ne_retire_pas_le_chef_projet(env):
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        rep = _client_pour(env["ct1"]).delete(_url(p1, f"{aff.id}/"), HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert _erreur(rep)["code"] == "chef_projet_protege"
        assert _erreur(rep)["message"] == MESSAGE_PROTEGE
        assert AffectationProjet.objects.filter(id=aff.id).exists()
        p1.refresh_from_db()
        assert p1.chef_projet_id == env["cp1"].id


def test_ct_ne_retire_pas_le_chef_projet_en_suppression_logique(env):
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        rep = _client_pour(env["ct1"]).delete(_url(p1, f"{aff.id}/?hard=false"), HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert _erreur(rep)["code"] == "chef_projet_protege"
        aff.refresh_from_db()
        assert aff.est_actif is True


def test_dg_retire_le_chef_projet(env):
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        rep = _client_pour(env["dg"]).delete(_url(p1, f"{aff.id}/"), HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT
        p1.refresh_from_db()
        assert p1.chef_projet is None


def test_administrateur_retire_le_chef_projet(env):
    """L'administrateur est de portée entreprise et détient `projets.affecter_membres`."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        rep = _client_pour(env["ad"]).delete(_url(p1, f"{aff.id}/"), HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT


def test_autre_cp_ne_desactive_pas_le_chef_projet(env):
    """Un CP affecté a `projets.affecter_membres` mais n'est pas de portée entreprise."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        _affecter_en_renfort(p1, env["cp2"])
        rep = _client_pour(env["cp2"]).patch(
            _url(p1, f"{aff.id}/"), {"est_actif": False}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert _erreur(rep)["code"] == "chef_projet_protege"
        aff.refresh_from_db()
        assert aff.est_actif is True


@pytest.mark.parametrize("valeur", ["no", "off", "n", "f", "0", 0])
def test_desactivation_du_chef_projet_refusee_quelle_que_soit_l_ecriture(env, valeur):
    """La garde lit le booléen comme DRF : aucune écriture de « faux » ne la contourne."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        _affecter_en_renfort(p1, env["cp2"])
        rep = _client_pour(env["cp2"]).patch(
            _url(p1, f"{aff.id}/"), {"est_actif": valeur}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert _erreur(rep)["code"] == "chef_projet_protege"
        aff.refresh_from_db()
        assert aff.est_actif is True


@pytest.mark.parametrize("role", [" CP ", "cp", "CP	"])
def test_promotion_en_chef_projet_refusee_malgre_espaces_ou_casse(env, role):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        _affecter_en_renfort(p1, env["cp2"])
        aff_ct = AffectationProjet.objects.get(projet=p1, utilisateur=env["ct1"])
        rep = _client_pour(env["cp2"]).patch(
            _url(p1, f"{aff_ct.id}/"), {"role_projet": role}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        aff_ct.refresh_from_db()
        assert aff_ct.role_projet == RoleProjet.CONDUCTEUR_TRAVAUX


def test_ct_ne_desactive_ni_ne_retrograde_le_chef_projet(env):
    """Le CT du projet n'a pas `projets.affecter_membres` : la garde de la route répond 403."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        client = _client_pour(env["ct1"])
        for corps in ({"est_actif": False}, {"role_projet": "CT"}):
            rep = client.patch(_url(p1, f"{aff.id}/"), corps, format="json", HTTP_HOST=HOTE)
            assert rep.status_code == status.HTTP_403_FORBIDDEN, corps
        aff.refresh_from_db()
        assert aff.est_actif is True
        assert aff.role_projet == RoleProjet.CHEF_PROJET


def test_retrograder_le_chef_projet_est_refuse_en_403_et_non_en_400(env):
    """La protection passe avant la validation : pas de 400 `role_incoherent` à la place du 403."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        _affecter_en_renfort(p1, env["cp2"])
        rep = _client_pour(env["cp2"]).patch(
            _url(p1, f"{aff.id}/"), {"role_projet": "ct"}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert _erreur(rep)["code"] == "chef_projet_protege"
        aff.refresh_from_db()
        assert aff.role_projet == RoleProjet.CHEF_PROJET


def test_ct_ne_retire_pas_le_chef_projet_par_le_formulaire_du_projet(env):
    """`chef_projet_id`, ou son alias `chef_projet`, de PATCH /projets/{id}/ ne contourne pas
    la protection."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        client = _client_pour(env["ct1"])
        url = f"/api/v1/projets/{p1.id}/"

        for corps in (
            {"chef_projet_id": None},
            {"chef_projet_id": str(env["cp3"].id)},
            {"chef_projet": None},
            {"chef_projet": str(env["cp3"].id)},
        ):
            rep = client.patch(url, corps, format="json", HTTP_HOST=HOTE)
            assert rep.status_code == status.HTTP_403_FORBIDDEN, corps
            assert _erreur(rep)["code"] == "chef_projet_protege"
            p1.refresh_from_db()
            aff.refresh_from_db()
            assert p1.chef_projet_id == env["cp1"].id
            assert aff.est_actif is True

        # Les autres champs du formulaire, et un `chef_projet_id` inchangé, restent permis.
        rep = client.patch(
            url,
            {"description": "Mise à jour", "chef_projet_id": str(env["cp1"].id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_200_OK, rep.json()


def test_alias_chef_projet_inchange_reste_permis(env):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        rep = _client_pour(env["ct1"]).patch(
            f"/api/v1/projets/{p1.id}/",
            {"chef_projet": str(env["cp1"].id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_200_OK, rep.json()
        p1.refresh_from_db()
        assert p1.chef_projet_id == env["cp1"].id


def test_dg_remplace_le_chef_projet_par_le_formulaire_du_projet(env):
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        rep = _client_pour(env["dg"]).patch(
            f"/api/v1/projets/{p1.id}/",
            {"chef_projet_id": str(env["cp3"].id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_200_OK, rep.json()
        p1.refresh_from_db()
        aff.refresh_from_db()
        assert p1.chef_projet_id == env["cp3"].id
        assert aff.est_actif is False


def test_dg_desactive_le_chef_projet(env):
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        rep = _client_pour(env["dg"]).patch(
            _url(p1, f"{aff.id}/"), {"est_actif": False}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_200_OK
        aff.refresh_from_db()
        assert aff.est_actif is False


def test_changer_les_dates_du_chef_projet_reste_permis(env):
    """Seuls le retrait, la désactivation, le changement de rôle et la nomination sont protégés."""
    with schema_context(SCHEMA):
        p1, aff = env["projet1"], env["aff_cp1"]
        _affecter_en_renfort(p1, env["cp2"])
        rep = _client_pour(env["cp2"]).patch(
            _url(p1, f"{aff.id}/"), {"date_fin": "2027-06-30"}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_200_OK


def test_cp_ne_nomme_pas_un_chef_projet(env):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        rep = _client_pour(env["cp1"]).post(
            _url(p1),
            {"utilisateur_id": str(env["cp3"].id), "role_projet": RoleProjet.CHEF_PROJET},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert _erreur(rep)["code"] == "chef_projet_protege"
        assert not AffectationProjet.objects.filter(projet=p1, utilisateur=env["cp3"]).exists()


@pytest.mark.parametrize("acteur", ["dg", "ad"])
def test_direction_nomme_un_chef_projet(env, acteur):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        rep = _client_pour(env[acteur]).post(
            _url(p1),
            {"utilisateur_id": str(env["cp3"].id), "role_projet": RoleProjet.CHEF_PROJET},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_201_CREATED
        p1.refresh_from_db()
        assert p1.chef_projet_id == env["cp3"].id


def test_cp_affecte_toujours_un_chef_de_chantier(env):
    """La protection ne touche que l'affectation du chef de projet."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        rep = _client_pour(env["cp1"]).post(
            _url(p1),
            {"utilisateur_id": str(env["cc1"].id), "role_projet": RoleProjet.CHEF_CHANTIER},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_201_CREATED


def test_champ_modifiable_selon_l_utilisateur(env):
    with schema_context(SCHEMA):
        p1, cp1 = env["projet1"], env["cp1"]
        _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)

        def modifiables(acteur):
            rep = _client_pour(env[acteur]).get(_url(p1), HTTP_HOST=HOTE)
            assert rep.status_code == status.HTTP_200_OK
            return {a["utilisateur"]["id"]: a["modifiable"] for a in rep.json()}

        # Le CT et le CC n'ont pas `projets.affecter_membres` : rien n'est modifiable pour eux.
        assert set(modifiables("ct1").values()) == {False}
        assert set(modifiables("cc1").values()) == {False}

        # Un CP en renfort affecte les membres, mais pas le chef de projet.
        _affecter_en_renfort(p1, env["cp2"])
        pour_cp = modifiables("cp2")
        assert pour_cp[str(cp1.id)] is False
        assert pour_cp[str(env["cc1"].id)] is True

        for direction in ("dg", "ad"):
            pour_direction = modifiables(direction)
            assert pour_direction[str(cp1.id)] is True
            assert pour_direction[str(env["cc1"].id)] is True


# --------------------------------------------------------------------------
# (2) Le lot du chef de chantier
# --------------------------------------------------------------------------
def test_chef_chantier_avec_lot(env):
    with schema_context(SCHEMA):
        p1, lot = env["projet1"], env["lot1"]
        rep = _client_pour(env["dg"]).post(
            _url(p1),
            {
                "utilisateur_id": str(env["cc1"].id),
                "role_projet": RoleProjet.CHEF_CHANTIER,
                "lot_id": str(lot.id),
                "zone": "Zone libre ignorée",
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_201_CREATED, rep.json()
        data = rep.json()
        assert data["lot"] == {"id": str(lot.id), "code": "L01", "libelle": "Gros œuvre"}
        # Le lot fixe la zone : code et libellé.
        assert data["zone"] == "L01 — Gros œuvre"
        assert data["modifiable"] is True


def test_chef_chantier_sans_lot_garde_la_zone(env):
    with schema_context(SCHEMA):
        rep = _client_pour(env["dg"]).post(
            _url(env["projet1"]),
            {
                "utilisateur_id": str(env["cc1"].id),
                "role_projet": RoleProjet.CHEF_CHANTIER,
                "zone": "Bâtiment B",
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_201_CREATED
        assert rep.json()["lot"] is None
        assert rep.json()["zone"] == "Bâtiment B"


def test_lot_d_un_autre_projet_refuse(env):
    with schema_context(SCHEMA):
        rep = _client_pour(env["dg"]).post(
            _url(env["projet1"]),
            {
                "utilisateur_id": str(env["cc1"].id),
                "role_projet": RoleProjet.CHEF_CHANTIER,
                "lot_id": str(env["lot_autre"].id),
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_400_BAD_REQUEST
        assert "n'appartient pas à ce projet" in _erreur(rep)["message"]
        assert not AffectationProjet.objects.filter(
            projet=env["projet1"], utilisateur=env["cc1"]
        ).exists()


def test_lot_supprime_refuse(env):
    with schema_context(SCHEMA):
        env["lot2"].delete()
        rep = _client_pour(env["dg"]).post(
            _url(env["projet1"]),
            {
                "utilisateur_id": str(env["cc1"].id),
                "role_projet": RoleProjet.CHEF_CHANTIER,
                "lot_id": str(env["lot2"].id),
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_400_BAD_REQUEST


def test_lot_refuse_pour_un_autre_role_que_chef_de_chantier(env):
    with schema_context(SCHEMA):
        rep = _client_pour(env["dg"]).post(
            _url(env["projet1"]),
            {
                "utilisateur_id": str(env["ct2"].id),
                "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
                "lot_id": str(env["lot1"].id),
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == status.HTTP_400_BAD_REQUEST
        assert "ne concerne qu'un chef de chantier" in _erreur(rep)["message"]


def test_modifier_puis_retirer_le_lot(env):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff = _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER, zone="Ancienne zone")
        client = _client_pour(env["dg"])

        rep = client.patch(
            _url(p1, f"{aff.id}/"), {"lot_id": str(env["lot2"].id)}, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_200_OK, rep.json()
        assert rep.json()["lot"]["code"] == "L02"
        assert rep.json()["zone"] == "L02 — Électricité"

        refus = client.patch(
            _url(p1, f"{aff.id}/"),
            {"lot_id": str(env["lot_autre"].id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert refus.status_code == status.HTTP_400_BAD_REQUEST
        aff.refresh_from_db()
        assert aff.lot_id == env["lot2"].id

        rep = client.patch(_url(p1, f"{aff.id}/"), {"lot_id": None}, format="json", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        assert rep.json()["lot"] is None


def test_lecture_du_lot_supprime_renvoie_null(env):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER, lot=env["lot2"])
        env["lot2"].delete()
        rep = _client_pour(env["dg"]).get(_url(p1), HTTP_HOST=HOTE)
        cc = [a for a in rep.json() if a["utilisateur"]["id"] == str(env["cc1"].id)]
        assert cc[0]["lot"] is None


def test_rapport_journalier_nomme_le_chef_de_chantier_du_lot(env):
    """Chaque lot porte le chef de chantier rattaché ; à défaut, celui sans lot du projet."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER, lot=env["lot1"])
        _affecter(p1, env["cc2"], RoleProjet.CHEF_CHANTIER)
        contexte = contexte_projet(p1, date.today())
        chefs = {lot["code"]: lot["chef_chantier_nom"] for lot in contexte["lots"]}
        assert chefs["L01"] == "Test CC Un"
        assert chefs["L02"] == "Test CC Deux"


def test_rapport_journalier_ne_prete_pas_le_chef_d_un_autre_lot(env):
    """Sans chef de chantier hors lot, un lot sans chef rattaché reste vide."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER, lot=env["lot1"])
        contexte = contexte_projet(p1, date.today())
        chefs = {lot["code"]: lot["chef_chantier_nom"] for lot in contexte["lots"]}
        assert chefs["L01"] == "Test CC Un"
        assert chefs["L02"] == ""


# --------------------------------------------------------------------------
# (3) Les équipes
# --------------------------------------------------------------------------
def _equipe(nom, **champs):
    return {"nom": nom, "nature": "INTERNE", "corps_etat": "Maçonnerie", **champs}


def test_gerer_equipes_par_defaut_pour_le_cp_et_le_ct():
    for code in ("DG", "AD", "CP", "CT"):
        assert "projets.gerer_equipes" in PERMISSIONS_DEFAUT_ROLES[code]["projets"]
    assert "projets.gerer_equipes" not in PERMISSIONS_DEFAUT_ROLES["CC"]["projets"]


def test_plusieurs_equipes_et_un_collaborateur_dans_deux_equipes(env):
    with schema_context(SCHEMA):
        p1, cc1 = env["projet1"], env["cc1"]
        _affecter(p1, cc1, RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["cp1"])
        base = f"/api/v1/projets/{p1.id}/equipes/"

        premiere = client.post(
            base,
            _equipe("Équipe A", membres=[{"utilisateur_id": str(cc1.id)}]),
            format="json",
            HTTP_HOST=HOTE,
        )
        seconde = client.post(
            base,
            _equipe("Équipe B", membres=[{"utilisateur_id": str(cc1.id)}]),
            format="json",
            HTTP_HOST=HOTE,
        )
        assert premiere.status_code == status.HTTP_201_CREATED, premiere.json()
        assert seconde.status_code == status.HTTP_201_CREATED, seconde.json()
        assert len(client.get(base, HTTP_HOST=HOTE).json()) == 2

        # Et par la route d'ajout d'un membre, dans une troisième équipe.
        troisieme = client.post(base, _equipe("Équipe C"), format="json", HTTP_HOST=HOTE)
        ajout = client.post(
            f"{base}{troisieme.json()['id']}/membres/",
            {"utilisateur_id": str(cc1.id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert ajout.status_code == status.HTTP_201_CREATED, ajout.json()


def test_membre_non_affecte_refuse_avec_un_message_clair(env):
    with schema_context(SCHEMA):
        p1, cc2 = env["projet1"], env["cc2"]
        client = _client_pour(env["cp1"])
        base = f"/api/v1/projets/{p1.id}/equipes/"

        creation = client.post(
            base,
            _equipe("Équipe A", membres=[{"utilisateur_id": str(cc2.id)}]),
            format="json",
            HTTP_HOST=HOTE,
        )
        assert creation.status_code == status.HTTP_400_BAD_REQUEST
        assert "n'est pas affecté à ce projet" in _erreur(creation)["message"]
        assert "Test CC Deux" in _erreur(creation)["message"]

        equipe = client.post(base, _equipe("Équipe B"), format="json", HTTP_HOST=HOTE)
        ajout = client.post(
            f"{base}{equipe.json()['id']}/membres/",
            {"utilisateur_id": str(cc2.id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert ajout.status_code == status.HTTP_400_BAD_REQUEST
        assert "n'est pas affecté à ce projet" in _erreur(ajout)["message"]


def test_candidats_aux_equipes(env):
    with schema_context(SCHEMA):
        p1, cc1, cc2 = env["projet1"], env["cc1"], env["cc2"]
        _affecter(p1, cc1, RoleProjet.CHEF_CHANTIER)
        # Affecté mais inactif sur le projet, puis affecté mais compte désactivé : exclus.
        _affecter(p1, cc2, RoleProjet.CHEF_CHANTIER)
        AffectationProjet.objects.filter(projet=p1, utilisateur=cc2).update(est_actif=False)
        desactive = _utilisateur("cc3.b4r@demo.ci", "CC Trois", RoleGlobal.CHEF_CHANTIER)
        _affecter(p1, desactive, RoleProjet.CHEF_CHANTIER)
        Utilisateur.tous_objets.filter(pk=desactive.pk).update(
            statut=StatutUtilisateur.DESACTIVE, is_active=False
        )

        client = _client_pour(env["cp1"])
        base = f"/api/v1/projets/{p1.id}/equipes/"
        a = client.post(
            base,
            _equipe("Équipe A", membres=[{"utilisateur_id": str(cc1.id)}]),
            format="json",
            HTTP_HOST=HOTE,
        ).json()
        b = client.post(
            base,
            _equipe("Équipe B", membres=[{"utilisateur_id": str(cc1.id)}]),
            format="json",
            HTTP_HOST=HOTE,
        ).json()

        rep = client.get(f"{base}candidats/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK, rep.json()
        candidats = {c["id"]: c for c in rep.json()}

        assert set(candidats) == {str(env["cp1"].id), str(env["ct1"].id), str(cc1.id)}
        assert candidats[str(cc1.id)]["nom_complet"] == "Test CC Un"
        assert candidats[str(cc1.id)]["role_projet"] == RoleProjet.CHEF_CHANTIER
        assert candidats[str(env["cp1"].id)]["role_projet"] == RoleProjet.CHEF_PROJET
        assert candidats[str(env["cp1"].id)]["equipes"] == []
        assert candidats[str(cc1.id)]["equipes"] == [
            {"id": a["id"], "nom": "Équipe A"},
            {"id": b["id"], "nom": "Équipe B"},
        ]


def test_candidats_reserves_a_gerer_equipes(env):
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)
        url = f"/api/v1/projets/{p1.id}/equipes/candidats/"
        # Un CC n'a pas `projets.gerer_equipes` ; un CP d'un autre projet n'y est pas affecté.
        assert _client_pour(env["cc1"]).get(url, HTTP_HOST=HOTE).status_code == 403
        assert _client_pour(env["cp2"]).get(url, HTTP_HOST=HOTE).status_code == 403
        assert _client_pour(env["ct1"]).get(url, HTTP_HOST=HOTE).status_code == 200
