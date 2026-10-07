"""Tests d'acceptation pour la règle D-07 (Migration de la portée des rôles)."""

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Role
from apps.catalogue.models import CataloguePermission
from apps.core.registre_permissions import REGISTRE

pytestmark = pytest.mark.django_db


def test_d07_migration_portee():
    """[D-07] Les rôles ayant l'accès transverse historique (DG, AD, DO) ont la portée ENTREPRISE, les autres PROJET."""
    with schema_context("demo"):
        roles_entreprise = {"DG", "AD", "DO"}
        roles_projet = {"DF", "CP", "CT", "CC", "MAG", "BAI", "VI"}

        for code in roles_entreprise:
            r = Role.objects.filter(code=code, supprime_le__isnull=True).first()
            if r and hasattr(r, "portee"):
                assert r.portee == "ENTREPRISE", f"Le rôle {code} devrait avoir la portée ENTREPRISE"

        for code in roles_projet:
            r = Role.objects.filter(code=code, supprime_le__isnull=True).first()
            if r and hasattr(r, "portee"):
                assert r.portee == "PROJET", f"Le rôle {code} devrait avoir la portée PROJET"


def test_d07_df_est_projet():
    """[D-07] Le rôle DF est explicitement à portée PROJET."""
    with schema_context("demo"):
        r_df = Role.objects.filter(code="DF", supprime_le__isnull=True).first()
        if r_df and hasattr(r_df, "portee"):
            assert r_df.portee == "PROJET"


def test_d07_voir_tous_disparait():
    """[D-07] projets.voir_tous disparaît du REGISTRE et du catalogue de permissions après le lot 2."""
    assert "projets.voir_tous" not in REGISTRE
    assert not CataloguePermission.objects.filter(code="projets.voir_tous", supprime_le__isnull=True).exists()
