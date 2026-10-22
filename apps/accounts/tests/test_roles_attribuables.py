"""Liste des rôles attribuables (?attribuables=1) pour la sélection du rôle à l'ajout d'un collaborateur."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.droits import permissions_du_role
from apps.core.enums import RoleGlobal, StatutUtilisateur

from apps.accounts.tests.test_parametres_roles import (  # noqa: F401
    HOTE,
    SCHEMA,
    admin_user,
    client_tenant,
    dg_user,
)


def _codes(client):
    rep = client.get("/api/v1/parametres/roles/?attribuables=1")
    assert rep.status_code == status.HTTP_200_OK
    return {r["code"] for r in rep.json()}


@pytest.mark.django_db
def test_dg_voit_tous_les_roles_sauf_dg(client_tenant, dg_user):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
    client_tenant.force_authenticate(user=dg_user)
    codes = _codes(client_tenant)
    assert "DG" not in codes
    assert "AD" in codes


@pytest.mark.django_db
def test_admin_ne_voit_ni_dg_ni_ad_ni_role_hors_de_ses_droits(client_tenant, admin_user):
    from apps.accounts.models import Role
    from apps.core.droits import permissions_effectives

    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        perms_ad = permissions_effectives(admin_user)
        hors_droits = {
            r.code
            for r in Role.objects.filter(supprime_le__isnull=True)
            if not permissions_du_role(r).issubset(perms_ad)
        }
    client_tenant.force_authenticate(user=admin_user)
    codes = _codes(client_tenant)
    assert not ({"DG", "AD"} & codes)
    assert not (hors_droits & codes)


@pytest.mark.django_db
def test_sans_filtre_la_liste_reste_complete(client_tenant, admin_user):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
    client_tenant.force_authenticate(user=admin_user)
    rep = client_tenant.get("/api/v1/parametres/roles/")
    assert rep.status_code == status.HTTP_200_OK
    assert {"AD"} <= {r["code"] for r in rep.json()}