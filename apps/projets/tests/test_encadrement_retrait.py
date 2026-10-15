"""Tests pour B4 : L'encadrement passe par les affectations et le retrait d'un collaborateur."""

from datetime import date

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet

SCHEMA = "demo"
HOTE = "demo.localhost"

pytestmark = pytest.mark.django_db


def _utilisateur(email, nom, role, **kwargs):
    u, _ = Utilisateur.tous_objets.get_or_create(
        email=email,
        defaults={
            "nom": nom,
            "prenom": "Test",
            "role_global": role,
            "statut": StatutUtilisateur.ACTIF,
            **kwargs,
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
        projet=projet, utilisateur=utilisateur, role_projet=role, est_actif=True, **champs
    )


def _client_pour(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def env(db):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        dg = _utilisateur("dg.b4@demo.ci", "Directeur", RoleGlobal.DIRECTEUR_GENERAL)
        dg.is_owner = True
        dg.save(update_fields=["is_owner"])

        ad = _utilisateur("ad.b4@demo.ci", "Admin", RoleGlobal.ADMIN)
        cp1 = _utilisateur("cp1.b4@demo.ci", "CP Un", RoleGlobal.CHEF_PROJET)
        cp2 = _utilisateur("cp2.b4@demo.ci", "CP Deux", RoleGlobal.CHEF_PROJET)
        ct1 = _utilisateur("ct1.b4@demo.ci", "CT Un", RoleGlobal.CONDUCTEUR_TRAVAUX)
        ct2 = _utilisateur("ct2.b4@demo.ci", "CT Deux", RoleGlobal.CONDUCTEUR_TRAVAUX)
        cc1 = _utilisateur("cc1.b4@demo.ci", "CC Un", RoleGlobal.CHEF_CHANTIER)
        cc2 = _utilisateur("cc2.b4@demo.ci", "CC Deux", RoleGlobal.CHEF_CHANTIER)
        vi = _utilisateur("vi.b4@demo.ci", "Visiteur", RoleGlobal.VISITEUR)

        projet1 = _projet("PRJ-B4-01", chef_projet=cp1, conducteur_travaux=ct1)
        _affecter(projet1, cp1, RoleProjet.CHEF_PROJET)
        _affecter(projet1, ct1, RoleProjet.CONDUCTEUR_TRAVAUX)

        projet2 = _projet("PRJ-B4-02", chef_projet=cp2, conducteur_travaux=ct2)
        _affecter(projet2, cp2, RoleProjet.CHEF_PROJET)
        _affecter(projet2, ct2, RoleProjet.CONDUCTEUR_TRAVAUX)

        return {
            "dg": dg,
            "ad": ad,
            "cp1": cp1,
            "cp2": cp2,
            "ct1": ct1,
            "ct2": ct2,
            "cc1": cc1,
            "cc2": cc2,
            "vi": vi,
            "projet1": projet1,
            "projet2": projet2,
        }


def test_chef_chantier_avec_zone(env):
    """POST affectation CC + zone -> 201 ; le projet renvoie la zone dans chefs_chantier."""
    with schema_context(SCHEMA):
        client = _client_pour(env["dg"])
        p1 = env["projet1"]
        payload = {
            "utilisateur_id": str(env["cc1"].id),
            "role_projet": RoleProjet.CHEF_CHANTIER,
            "zone": "Bâtiment B — Lot Gros Œuvre",
        }
        rep = client.post(
            f"/api/v1/projets/{p1.id}/affectations/", payload, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_201_CREATED
        aff_data = rep.json()
        assert aff_data["zone"] == "Bâtiment B — Lot Gros Œuvre"

        # Lecture du projet
        rep_p = client.get(f"/api/v1/projets/{p1.id}/", HTTP_HOST=HOTE)
        assert rep_p.status_code == status.HTTP_200_OK
        data_p = rep_p.json()
        cc_list = [
            c for c in data_p["chefs_chantier"] if c["utilisateur"]["id"] == str(env["cc1"].id)
        ]
        assert len(cc_list) == 1
        assert cc_list[0]["zone"] == "Bâtiment B — Lot Gros Œuvre"
        assert cc_list[0]["affectation_id"] == aff_data["id"]


def test_zone_refusee_hors_cc(env):
    """CT + zone -> 400."""
    with schema_context(SCHEMA):
        client = _client_pour(env["dg"])
        p1 = env["projet1"]
        payload = {
            "utilisateur_id": str(env["cc2"].id),
            "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
            "zone": "Zone Interdite pour CT",
        }
        rep = client.post(
            f"/api/v1/projets/{p1.id}/affectations/", payload, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_400_BAD_REQUEST
        data = rep.json()
        assert "zone" in str(data)


def test_autre_membre(env):
    """VI + fonction_membre='QHSE' -> 201 ; autres_membres contient la personne et sa fonction."""
    with schema_context(SCHEMA):
        client = _client_pour(env["dg"])
        p1 = env["projet1"]
        payload = {
            "utilisateur_id": str(env["vi"].id),
            "role_projet": RoleProjet.VISITEUR,
            "fonction_membre": "QHSE",
        }
        rep = client.post(
            f"/api/v1/projets/{p1.id}/affectations/", payload, format="json", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_201_CREATED
        aff_id = rep.json()["id"]
        assert rep.json()["fonction_membre"] == "QHSE"

        # Lecture du projet
        rep_p = client.get(f"/api/v1/projets/{p1.id}/", HTTP_HOST=HOTE)
        assert rep_p.status_code == status.HTTP_200_OK
        data_p = rep_p.json()
        assert "autres_membres" in data_p
        membres = [m for m in data_p["autres_membres"] if m["id"] == str(env["vi"].id)]
        assert len(membres) == 1
        assert membres[0]["fonction"] == "QHSE"
        assert membres[0]["affectation_id"] == aff_id


def test_dg_retire_partout(env):
    """DG non affecté -> 204 ; ligne absente de la base ; une ligne JournalAudit."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff = _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["dg"])

        rep = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT

        # Vérification effacement physique par défaut
        assert not AffectationProjet.objects.filter(id=aff.id).exists()
        assert not AffectationProjet.tous_objets.filter(id=aff.id).exists()

        # Vérification JournalAudit
        entrees = JournalAudit.objects.filter(
            type_entite="affectation_projet",
            action=ActionAudit.SUPPRESSION,
            entite_id=aff.id,
        )
        assert entrees.exists()
        valeur_avant = entrees.first().valeur_avant
        assert valeur_avant["utilisateur_id"] == str(env["cc1"].id)
        assert valeur_avant["role_projet"] == RoleProjet.CHEF_CHANTIER


def test_ad_retire_partout(env):
    """AD non affecté -> 204 ; effacement physique et audit."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff = _affecter(p1, env["cc2"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["ad"])

        rep = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT
        assert not AffectationProjet.objects.filter(id=aff.id).exists()


def test_cp_retire_sur_son_projet(env):
    """CP1 affecté sur projet 1 retire qqn sur projet 1 -> 204."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff = _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["cp1"])

        rep = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT
        assert not AffectationProjet.objects.filter(id=aff.id).exists()


def test_cp_refuse_ailleurs(env):
    """CP1 affecté sur projet 1 tente de retirer qqn sur projet 2 -> 403."""
    with schema_context(SCHEMA):
        p2 = env["projet2"]
        aff = _affecter(p2, env["cc2"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["cp1"])

        rep = client.delete(f"/api/v1/projets/{p2.id}/affectations/{aff.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert AffectationProjet.objects.filter(id=aff.id).exists()


def test_ct_retire_sur_son_projet(env):
    """CT1 affecté CT sur projet 1 retire un CC sur projet 1 -> 204."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff = _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["ct1"])

        rep = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT
        assert not AffectationProjet.objects.filter(id=aff.id).exists()


def test_ct_ne_retire_pas_ailleurs(env):
    """CT1 affecté CT sur projet 1 tente de retirer qqn sur projet 2 -> 403."""
    with schema_context(SCHEMA):
        p2 = env["projet2"]
        aff = _affecter(p2, env["cc2"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["ct1"])

        rep = client.delete(f"/api/v1/projets/{p2.id}/affectations/{aff.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        assert AffectationProjet.objects.filter(id=aff.id).exists()


def test_ct_toujours_refuse_en_post_et_patch(env):
    """Non-régression E-05 : CT n'a pas projets.affecter_membres et est refusé sur POST et PATCH."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        client = _client_pour(env["ct1"])

        # POST refusé
        rep_post = client.post(
            f"/api/v1/projets/{p1.id}/affectations/",
            {"utilisateur_id": str(env["cc2"].id), "role_projet": RoleProjet.CHEF_CHANTIER},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep_post.status_code == status.HTTP_403_FORBIDDEN

        # PATCH refusé
        aff = _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)
        rep_patch = client.patch(
            f"/api/v1/projets/{p1.id}/affectations/{aff.id}/",
            {"zone": "Nouvelle zone"},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep_patch.status_code == status.HTTP_403_FORBIDDEN


def test_personne_ne_se_retire(env):
    """CP (ou toute personne) qui tente de retirer sa propre affectation -> 403, message exact."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff_cp = AffectationProjet.objects.get(projet=p1, utilisateur=env["cp1"])
        client = _client_pour(env["cp1"])

        rep = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff_cp.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_403_FORBIDDEN
        data = rep.json()
        message = data.get("erreur", {}).get("message") or data.get("detail")
        assert message == "Vous ne pouvez pas vous retirer vous-même d'un projet."


def test_retrait_dernier_cp_vide_le_chef_projet(env):
    """Retirer le chef de projet vide le champ projet.chef_projet."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff_cp = AffectationProjet.objects.get(projet=p1, utilisateur=env["cp1"])
        client = _client_pour(env["dg"])

        rep = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff_cp.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_204_NO_CONTENT

        p1.refresh_from_db()
        assert p1.chef_projet is None


def test_reaffecter_apres_retrait(env):
    """Retirer puis réaffecter la même personne -> 201 (l'effacement physique le permet)."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        client = _client_pour(env["dg"])

        # 1. Première affectation
        rep1 = client.post(
            f"/api/v1/projets/{p1.id}/affectations/",
            {"utilisateur_id": str(env["cc1"].id), "role_projet": RoleProjet.CHEF_CHANTIER},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep1.status_code == status.HTTP_201_CREATED
        aff_id = rep1.json()["id"]

        # 2. Retrait (suppression physique par défaut)
        rep_del = client.delete(f"/api/v1/projets/{p1.id}/affectations/{aff_id}/", HTTP_HOST=HOTE)
        assert rep_del.status_code == status.HTTP_204_NO_CONTENT

        # 3. Réaffectation de la même personne
        rep2 = client.post(
            f"/api/v1/projets/{p1.id}/affectations/",
            {
                "utilisateur_id": str(env["cc1"].id),
                "role_projet": RoleProjet.CHEF_CHANTIER,
                "zone": "Zone après réaffectation",
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep2.status_code == status.HTTP_201_CREATED
        assert rep2.json()["zone"] == "Zone après réaffectation"


def test_hard_false_garde_la_revocation(env):
    """?hard=false -> révoqué logiquement, pas effacé."""
    with schema_context(SCHEMA):
        p1 = env["projet1"]
        aff = _affecter(p1, env["cc1"], RoleProjet.CHEF_CHANTIER)
        client = _client_pour(env["dg"])

        rep = client.delete(
            f"/api/v1/projets/{p1.id}/affectations/{aff.id}/?hard=false", HTTP_HOST=HOTE
        )
        assert rep.status_code == status.HTTP_204_NO_CONTENT

        # L'affectation existe toujours en base, mais marquée inactive et supprimée logiquement
        assert AffectationProjet.tous_objets.filter(id=aff.id).exists()
        aff_db = AffectationProjet.tous_objets.get(id=aff.id)
        assert aff_db.est_actif is False
        assert aff_db.supprime_le is not None
