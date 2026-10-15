"""Tests unitaires pour la restriction de renommage des projets (B3, US 3.2)."""

from datetime import date

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, RoleProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db


@pytest.fixture
def environnement_nom(schema_demo):
    """Prépare un environnement avec DG, AD, CP et un projet configuré."""
    from apps.accounts.services.roles import initialiser_roles_par_defaut

    initialiser_roles_par_defaut()

    def creer_utilisateur(nom, role):
        return Utilisateur.objects.create_user(
            email=f"{nom}.nom@demo.ci",
            password="Test12345!",
            nom=nom,
            role_global=role,
            statut=StatutUtilisateur.ACTIF,
        )

    dg = creer_utilisateur("dg", RoleGlobal.DIRECTEUR_GENERAL)
    ad = creer_utilisateur("ad", RoleGlobal.ADMIN)
    cp = creer_utilisateur("cp", RoleGlobal.CHEF_PROJET)
    tiers = Tiers.objects.create(raison_sociale="Client B3 Test", type_tiers="ENTREPRISE")

    projet = Projet.objects.create(
        reference="PRJ-B3-01",
        nom="Nom Initial du Projet",
        client=tiers,
        ville="Abidjan",
        chef_projet=cp,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=cp,
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
    )
    return {"dg": dg, "ad": ad, "cp": cp, "projet": projet}


def client_pour(user):
    c = APIClient(headers={"host": "demo.localhost"})
    c.force_authenticate(user=user)
    return c


def test_dg_renomme(environnement_nom):
    """Le DG peut renommer le projet, statut 200 et audit créé."""
    env = environnement_nom
    client = client_pour(env["dg"])

    url = f"/api/v1/projets/{env['projet'].id}/"
    res = client.patch(url, {"nom": "Nouveau Nom DG"}, format="json")

    assert res.status_code == status.HTTP_200_OK
    env["projet"].refresh_from_db()
    assert env["projet"].nom == "Nouveau Nom DG"

    # Vérification du journal d'audit
    audit = JournalAudit.objects.filter(
        type_entite="projet",
        entite_id=env["projet"].id,
        action=ActionAudit.MODIFICATION,
    ).latest("horodatage")

    assert audit.valeur_avant == {"nom": "Nom Initial du Projet"}
    assert audit.valeur_apres == {"nom": "Nouveau Nom DG"}
    assert audit.utilisateur_id == env["dg"].id


def test_ad_renomme(environnement_nom):
    """L'administrateur (AD) peut renommer le projet, statut 200."""
    env = environnement_nom
    client = client_pour(env["ad"])

    url = f"/api/v1/projets/{env['projet'].id}/"
    res = client.patch(url, {"nom": "Nouveau Nom AD"}, format="json")

    assert res.status_code == status.HTTP_200_OK
    env["projet"].refresh_from_db()
    assert env["projet"].nom == "Nouveau Nom AD"


def test_cp_ne_renomme_pas(environnement_nom):
    """Le Chef de Projet ne peut pas renommer le projet, 403 et message exact."""
    env = environnement_nom
    client = client_pour(env["cp"])

    url = f"/api/v1/projets/{env['projet'].id}/"
    res = client.patch(url, {"nom": "Tentative Nom CP"}, format="json")

    assert res.status_code == status.HTTP_403_FORBIDDEN
    msg_attendu = (
        "Seuls le Directeur Général et l'administrateur de "
        "l'entreprise peuvent renommer un projet."
    )
    assert res.data.get("detail") == msg_attendu or msg_attendu in str(res.data)

    env["projet"].refresh_from_db()
    assert env["projet"].nom == "Nom Initial du Projet"

    # Aucun audit de renommage créé
    audits = JournalAudit.objects.filter(
        type_entite="projet",
        entite_id=env["projet"].id,
        valeur_apres__has_key="nom",
    )
    assert not audits.exists()


def test_meme_nom_accepte_pour_le_cp(environnement_nom):
    """Un PATCH par le CP avec le même nom et un autre champ modifiable passe."""
    env = environnement_nom
    client = client_pour(env["cp"])

    url = f"/api/v1/projets/{env['projet'].id}/"
    res = client.patch(
        url,
        {
            "nom": "Nom Initial du Projet",
            "description": "Nouvelle description par le CP",
        },
        format="json",
    )

    assert res.status_code == status.HTTP_200_OK
    env["projet"].refresh_from_db()
    assert env["projet"].nom == "Nom Initial du Projet"
    assert env["projet"].description == "Nouvelle description par le CP"


def test_peut_renommer_dans_le_payload(environnement_nom):
    """Le champ calculé peut_renommer vaut True pour DG et AD, False pour CP."""
    env = environnement_nom
    url = f"/api/v1/projets/{env['projet'].id}/"

    # Pour DG
    res_dg = client_pour(env["dg"]).get(url)
    assert res_dg.status_code == status.HTTP_200_OK
    assert res_dg.data.get("peut_renommer") is True

    # Pour AD
    res_ad = client_pour(env["ad"]).get(url)
    assert res_ad.status_code == status.HTTP_200_OK
    assert res_ad.data.get("peut_renommer") is True

    # Pour CP
    res_cp = client_pour(env["cp"]).get(url)
    assert res_cp.status_code == status.HTTP_200_OK
    assert res_cp.data.get("peut_renommer") is False
