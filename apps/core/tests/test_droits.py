from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from apps.core.droits import APermission, a_permission, permissions_effectives
from apps.core.enums import RoleGlobal
from apps.core.registre_permissions import REGISTRE


@pytest.fixture
def mock_superuser():
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = True
    user.is_owner = False
    user.is_dg = False
    user.role_global = RoleGlobal.ADMIN
    user.role_personnalise = None
    return user


@pytest.fixture
def mock_dg():
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.is_owner = True
    user.is_dg = True
    user.role_global = RoleGlobal.DIRECTEUR_GENERAL
    user.role_personnalise = None
    return user


@pytest.fixture
def mock_collaborateur():
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.is_owner = False
    user.is_dg = False
    user.role_global = RoleGlobal.CONDUCTEUR_TRAVAUX
    user.role_personnalise = None
    return user


def test_permissions_effectives_non_authentifie():
    assert permissions_effectives(None) == set()
    anon = MagicMock(is_authenticated=False)
    assert permissions_effectives(anon) == set()


def test_permissions_effectives_superuser(mock_superuser):
    perms = permissions_effectives(mock_superuser)
    assert perms == set(REGISTRE.keys())
    assert a_permission(mock_superuser, "projets.creer") is True
    assert a_permission(mock_superuser, "administration.roles_gerer") is True


def test_permissions_effectives_dg_tous_modules(mock_dg):
    with patch("apps.core.droits._obtenir_modules_actifs", return_value={"projets", "chantier", "administration"}):
        perms = permissions_effectives(mock_dg)
        assert "projets.lire" in perms
        assert "projets.changer_statut" in perms
        assert "chantier.valider" in perms
        assert "administration.roles_gerer" in perms
        # Tiers et pilotage ne sont pas actifs dans ce mock
        assert "tiers.lire" not in perms
        assert "pilotage.lire" not in perms


def test_permissions_effectives_collaborateur_codes(mock_collaborateur):
    role_mock = MagicMock()
    role_mock.code = "CT"
    role_mock.est_actif = True
    mock_collaborateur.role_personnalise = role_mock

    rmp_projets = MagicMock()
    rmp_projets.module_catalogue_id = None
    rmp_projets.module_id = "uuid1"
    rmp_projets.module.code = "projets"
    rmp_projets.permissions_catalogue.filter.return_value.values_list.return_value = [
        "projets.lire",
        "projets.ecrire",
    ]

    rmp_chantier = MagicMock()
    rmp_chantier.module_catalogue_id = None
    rmp_chantier.module_id = "uuid2"
    rmp_chantier.module.code = "chantier"
    rmp_chantier.permissions_catalogue.filter.return_value.values_list.return_value = [
        "chantier.lire",
        "chantier.rediger",
        "chantier.valider",
    ]

    qs_mock = MagicMock()
    qs_mock.select_related.return_value = qs_mock
    qs_mock.exists.return_value = True
    qs_mock.__iter__.return_value = iter([rmp_projets, rmp_chantier])

    with (
        patch("apps.core.droits._obtenir_modules_actifs", return_value={"projets", "chantier", "administration"}),
        patch("apps.accounts.models.RoleModulePermission.objects.filter", return_value=qs_mock),
    ):
        perms = permissions_effectives(mock_collaborateur)
        assert "projets.lire" in perms
        assert "projets.ecrire" in perms
        assert "projets.creer" not in perms
        assert "projets.changer_statut" not in perms
        assert "projets.voir_tous" not in perms
        assert "chantier.lire" in perms
        assert "chantier.rediger" in perms
        assert "chantier.valider" in perms
        assert "administration.roles_gerer" not in perms


def test_a_permission_permission_class(mock_dg, mock_collaborateur):
    factory = APIRequestFactory()
    perm_instance = APermission.pour("projets.changer_statut")()

    class SimpleView:
        pass

    view = SimpleView()

    request1 = factory.get("/api/v1/projets/")
    request1.user = mock_collaborateur
    with patch("apps.core.droits.permissions_effectives", return_value={"projets.lire", "projets.ecrire"}):
        assert perm_instance.has_permission(request1, view) is False

    request2 = factory.get("/api/v1/projets/")
    request2.user = mock_collaborateur
    with patch("apps.core.droits.permissions_effectives", return_value={"projets.lire", "projets.changer_statut"}):
        assert perm_instance.has_permission(request2, view) is True
