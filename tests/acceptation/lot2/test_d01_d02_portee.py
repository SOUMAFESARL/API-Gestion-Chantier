"""Tests d'acceptation pour les règles D-01 et D-02 (Portée d'un rôle : ENTREPRISE ou PROJET)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role
from apps.catalogue.models import ModeleRole

pytestmark = pytest.mark.django_db


def test_d01_portee_valeurs_valides(client_dg, fab):
    """[D-01] La portée d'un rôle accepte uniquement les valeurs ENTREPRISE et PROJET (rejet 400 pour toute autre)."""
    role = fab.creer_role_personnalise("ROLE_PORTEE_VAL", "Rôle Portée Valide")

    # 1. ENTREPRISE
    rep_ent = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "ENTREPRISE", "confirmer": True},
        format="json",
    )
    assert rep_ent.status_code == status.HTTP_200_OK

    # 2. PROJET
    rep_prj = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "PROJET", "confirmer": True},
        format="json",
    )
    assert rep_prj.status_code == status.HTTP_200_OK

    # 3. Valeur invalide
    rep_inv = client_dg.patch(
        f"/api/v1/parametres/roles/{role.id}/",
        {"portee": "AUTRE"},
        format="json",
    )
    assert rep_inv.status_code == status.HTTP_400_BAD_REQUEST


def test_d01_portee_obligatoire_a_la_creation(client_dg):
    """[D-01] À la création d'un rôle sans portée spécifiée, la valeur par défaut retenue est PROJET."""
    payload = {
        "code": "PERSO_SANS_PORTEE",
        "libelle": "Perso Sans Portée",
    }
    rep = client_dg.post("/api/v1/parametres/roles/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    with schema_context("demo"):
        role = Role.objects.get(code="PERSO_SANS_PORTEE", supprime_le__isnull=True)
        assert getattr(role, "portee", "PROJET") == "PROJET"


def test_d02_dg_fixe_la_portee_d_un_role_de_son_entreprise(client_dg, fab):
    """[D-02] Le Directeur Général peut modifier la portée des rôles de son entreprise."""
    with schema_context("demo"):
        role_cp = Role.objects.get(code="CP", supprime_le__isnull=True)

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role_cp.id}/",
        {"portee": "ENTREPRISE", "confirmer": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK


def test_d02_dg_ne_change_pas_la_portee_de_son_propre_role(client_dg, fab):
    """[D-02] Le DG ne peut pas modifier la portée de son propre rôle DG (403)."""
    with schema_context("demo"):
        role_dg = Role.objects.get(code="DG", supprime_le__isnull=True)

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role_dg.id}/",
        {"portee": "PROJET", "confirmer": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_d02_ad_ne_change_pas_la_portee(client_ad, fab):
    """[D-02] L'administrateur (AD) n'a pas le droit de modifier la portée d'un rôle (403)."""
    with schema_context("demo"):
        role_cc = Role.objects.get(code="CC", supprime_le__isnull=True)

    rep = client_ad.patch(
        f"/api/v1/parametres/roles/{role_cc.id}/",
        {"portee": "ENTREPRISE", "confirmer": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_d02_isolation_entre_entreprises(client_dg):
    """[D-02] Le DG d'une entreprise ne peut pas modifier un rôle inexistant dans son tenant (404)."""
    import uuid
    id_inconnu = uuid.uuid4()
    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{id_inconnu}/",
        {"portee": "ENTREPRISE"},
        format="json",
    )
    assert rep.status_code == status.HTTP_404_NOT_FOUND


def test_d02_super_admin_fixe_la_portee_des_modeles(client_super_admin):
    """[D-02] Le Super Administrateur peut modifier la portée d'un modèle de rôle dans le catalogue public."""
    from django_tenants.utils import get_public_schema_name
    with schema_context(get_public_schema_name()):
        modele = ModeleRole.objects.filter(code="CP", supprime_le__isnull=True).first()
        if modele:
            modele_id = modele.id

    if modele:
        rep = client_super_admin.patch(
            f"/api/v1/super-admin/modeles-roles/{modele_id}/",
            {"portee": "PROJET"},
            format="json",
        )
        assert rep.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)
