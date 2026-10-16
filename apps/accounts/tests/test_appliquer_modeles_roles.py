import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Role, RoleModulePermission
from apps.accounts.services.roles import (
    appliquer_modeles_roles,
    modifier_role,
)

SCHEMA = "demo"


@pytest.mark.django_db
def test_appliquer_modeles_roles_cree_les_roles_avec_bons_codes():
    with schema_context(SCHEMA):
        roles = appliquer_modeles_roles()
        assert len(roles) >= 10

        role_ad = Role.objects.get(code="AD")
        rmp_ad_tiers = RoleModulePermission.objects.get(role=role_ad, module__code="tiers")
        codes_ad_tiers = set(rmp_ad_tiers.permissions_catalogue.values_list("code", flat=True))
        assert "tiers.lire" in codes_ad_tiers
        assert "tiers.ecrire" in codes_ad_tiers

        role_cc = Role.objects.get(code="CC")
        rmp_cc_projets = RoleModulePermission.objects.get(role=role_cc, module__code="projets")
        codes_cc_projets = set(rmp_cc_projets.permissions_catalogue.values_list("code", flat=True))
        assert "projets.lire" in codes_cc_projets

        role_dg = Role.objects.get(code="DG")
        rmp_dg_projets = RoleModulePermission.objects.get(role=role_dg, module__code="projets")
        codes_dg_projets = set(rmp_dg_projets.permissions_catalogue.values_list("code", flat=True))
        assert "projets.lire" in codes_dg_projets
        assert "projets.changer_statut" in codes_dg_projets


@pytest.mark.django_db
def test_modifier_role_autorise_restreindre_codes():
    with schema_context(SCHEMA):
        appliquer_modeles_roles()
        role_ct = Role.objects.get(code="CT")
        role_modifie = modifier_role(
            role=role_ct,
            permissions_modules={"projets": ["projets.lire"]},
        )
        rmp = RoleModulePermission.objects.get(role=role_modifie, module__code="projets")
        assert list(rmp.permissions_catalogue.values_list("code", flat=True)) == ["projets.lire"]
