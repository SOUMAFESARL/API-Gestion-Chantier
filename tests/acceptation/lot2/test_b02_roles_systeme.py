"""Tests d'acceptation pour la règle B-02 (Codes de rôles système souverains)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role, Utilisateur

pytestmark = pytest.mark.django_db

ROLES_SYSTEME_ATTENDUS = {"DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"}


def test_b02_dix_roles_systeme():
    """[B-02] L'entreprise possède exactement les 10 rôles système souverains."""
    with schema_context("demo"):
        codes_systeme = set(
            Role.objects.filter(est_systeme=True, supprime_le__isnull=True).values_list("code", flat=True)
        )
        assert codes_systeme == ROLES_SYSTEME_ATTENDUS


def test_b02_pas_de_moa_moe():
    """[B-02] Aucun rôle système n'a pour code MOA ou MOE."""
    with schema_context("demo"):
        codes_systeme = set(
            Role.objects.filter(est_systeme=True, supprime_le__isnull=True).values_list("code", flat=True)
        )
        assert "MOA" not in codes_systeme
        assert "MOE" not in codes_systeme


def test_b02_enum_non_source_de_verite(fab):
    """[B-02] Modifier directement le champ role en base met à jour le profil et les permissions effectives."""
    user = fab.utilisateur_avec_role("CC", email="user.enum.test@demo.ci")
    with schema_context("demo"):
        role_df = Role.objects.get(code="DF", supprime_le__isnull=True)
        u = Utilisateur.objects.get(id=user.id)
        u.role = role_df
        u.save()

    client = fab.client_pour(user)
    rep = client.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data.get("role_global") == "DF"
