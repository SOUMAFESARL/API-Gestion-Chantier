import pytest
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context

from apps.accounts.models import Module, Role, RoleModulePermission
from apps.accounts.services.roles import (
    appliquer_modeles_roles,
    creer_role,
    modifier_role,
)

SCHEMA = "demo"


@pytest.mark.django_db
def test_appliquer_modeles_roles_cree_les_roles_avec_bons_niveaux():
    with schema_context(SCHEMA):
        roles = appliquer_modeles_roles()
        assert len(roles) >= 10

        role_ad = Role.objects.get(code="AD")
        rmp_ad_tiers = RoleModulePermission.objects.get(role=role_ad, module__code="tiers")
        assert rmp_ad_tiers.niveau == 2

        role_cc = Role.objects.get(code="CC")
        rmp_cc_projets = RoleModulePermission.objects.get(role=role_cc, module__code="projets")
        assert rmp_cc_projets.niveau == 1

        role_dg = Role.objects.get(code="DG")
        rmp_dg_projets = RoleModulePermission.objects.get(role=role_dg, module__code="projets")
        assert rmp_dg_projets.niveau == 3


@pytest.mark.django_db
def test_modifier_role_interdit_depasser_plafond_modele():
    with schema_context(SCHEMA):
        appliquer_modeles_roles()
        role_ct = Role.objects.get(code="CT")
        # Le plafond de CT sur tiers est 1 (Lecture seule).
        # Tenter de lui accorder ECRITURE (niveau 2) ou VALIDATION (niveau 3) doit être refusé.
        with pytest.raises(ValidationError) as exc:
            modifier_role(
                role=role_ct,
                permissions_modules={"tiers": ["LECTURE", "ECRITURE"]},
            )
        assert "dépasse le plafond autorisé" in str(exc.value)


@pytest.mark.django_db
def test_modifier_role_autorise_restreindre_niveau():
    with schema_context(SCHEMA):
        appliquer_modeles_roles()
        role_ct = Role.objects.get(code="CT")
        # Le plafond de CT sur projets est 2. Le restreindre à 1 (Lecture) est autorisé.
        role_modifie = modifier_role(
            role=role_ct,
            permissions_modules={"projets": ["LECTURE"]},
        )
        rmp = RoleModulePermission.objects.get(role=role_modifie, module__code="projets")
        assert rmp.niveau == 1
