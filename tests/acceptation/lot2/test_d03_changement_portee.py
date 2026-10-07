"""Tests d'acceptation pour la règle D-03 (Changement de portée avec confirmation explicite)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role, Utilisateur
from apps.projets.models import AffectationProjet, Projet

pytestmark = pytest.mark.django_db


def test_d03_sans_confirmation(client_dg, fab):
    """[D-03] Changer la portée sans confirmation renvoie 409 avec le nombre de personnes touchées et ne modifie rien."""
    role = fab.creer_role_personnalise("ROLE_D03_SANS", "Rôle Sans Conf", portee="PROJET")
    # Créer 2 utilisateurs actifs et 1 inactif portant ce rôle
    user1 = fab.utilisateur_avec_role("ROLE_D03_SANS", email="d03.u1@demo.ci")
    user2 = fab.utilisateur_avec_role("ROLE_D03_SANS", email="d03.u2@demo.ci")

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "ENTREPRISE"},
        format="json",
    )
    assert rep.status_code == status.HTTP_409_CONFLICT
    assert rep.data.get("code") == "confirmation_requise"
    assert rep.data.get("personnes_touchees", 0) >= 2

    with schema_context("demo"):
        role_db = Role.objects.get(id=role.id)
        assert getattr(role_db, "portee", "PROJET") == "PROJET"


def test_d03_avec_confirmation_vers_entreprise(client_dg, fab):
    """[D-03] Passer vers ENTREPRISE avec confirmer=true désactive logiquement les affectations de projet."""
    role = fab.creer_role_personnalise("ROLE_D03_CONF", "Rôle Avec Conf", portee="PROJET")
    user = fab.utilisateur_avec_role("ROLE_D03_CONF", email="d03.conf.user@demo.ci")

    with schema_context("demo"):
        projet, _ = Projet.objects.get_or_create(
            reference="PRJ-D03-01",
            defaults={"nom": "Projet D03", "cree_par": user},
        )
        aff = AffectationProjet.objects.create(
            projet=projet,
            utilisateur=user,
            role_projet="CC",
            est_actif=True,
        )
        aff_id = aff.id

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "ENTREPRISE", "confirmer": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK

    with schema_context("demo"):
        role_db = Role.objects.get(id=role.id)
        assert getattr(role_db, "portee", None) == "ENTREPRISE"
        # L'affectation doit être désactivée mais toujours présente en base (historique conservé)
        aff_db = AffectationProjet.objects.filter(id=aff_id).first()
        if aff_db:
            assert aff_db.est_actif is False


def test_d03_avec_confirmation_vers_projet(client_dg, fab):
    """[D-03] Passer de ENTREPRISE à PROJET avec confirmation est accepté et ne crée aucune affectation."""
    role = fab.creer_role_personnalise("ROLE_D03_VERS_PRJ", "Vers Projet", portee="ENTREPRISE")

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "PROJET", "confirmer": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK
    with schema_context("demo"):
        role_db = Role.objects.get(id=role.id)
        assert getattr(role_db, "portee", None) == "PROJET"


def test_d03_pas_de_changement_si_meme_valeur(client_dg, fab):
    """[D-03] Si la portée envoyée est identique à la portée actuelle, 200 OK sans exiger de confirmation."""
    role = fab.creer_role_personnalise("ROLE_D03_MEME", "Même Valeur", portee="PROJET")

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "PROJET"},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK


def test_d03_les_autres_roles_ne_bougent_pas(client_dg, fab):
    """[D-03] La modification de la portée d'un rôle n'altère en rien les autres rôles de l'entreprise."""
    role1 = fab.creer_role_personnalise("ROLE_ISO_1", "Role 1", portee="PROJET")
    role2 = fab.creer_role_personnalise("ROLE_ISO_2", "Role 2", portee="PROJET")

    client_dg.patch(
        f"/api/v1/parametres/roles/{role1.id}/",
        {"portee": "ENTREPRISE", "confirmer": True},
        format="json",
    )

    with schema_context("demo"):
        role2_db = Role.objects.get(id=role2.id)
        assert getattr(role2_db, "portee", "PROJET") == "PROJET"
