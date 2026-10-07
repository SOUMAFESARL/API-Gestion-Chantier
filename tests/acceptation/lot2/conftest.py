"""
conftest du LOT 2 : VERROUILLÉ. Gemini ne le modifie jamais.
Toute la dépendance aux noms réels du dépôt est dans tests/fabriques_lot2.py.
"""
import sys
from pathlib import Path

import pytest
from django_tenants.utils import get_public_schema_name, schema_context

_TESTS = Path(__file__).resolve().parents[2]  # .../tests
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))


@pytest.fixture(autouse=True)
def _acces_base(db):
    """Accès à la base pour tous les tests du lot et initialisation des rôles."""
    from django.core.management import call_command
    with schema_context(get_public_schema_name()):
        call_command("synchroniser_catalogue_permissions")
    with schema_context("demo"):
        from apps.accounts.models import Role
        if not Role.objects.filter(supprime_le__isnull=True).exists():
            from apps.accounts.services.roles import initialiser_roles_par_defaut
            initialiser_roles_par_defaut()
    yield


@pytest.fixture
def fab():
    import fabriques_lot2

    return fabriques_lot2


@pytest.fixture
def dg(fab):
    return fab.obtenir_dg()


@pytest.fixture
def client_dg(fab, dg):
    return fab.client_pour(dg)


@pytest.fixture
def ad(fab):
    return fab.utilisateur_avec_role("AD")


@pytest.fixture
def client_ad(fab, ad):
    return fab.client_pour(ad)


@pytest.fixture
def super_admin(fab):
    return fab.obtenir_super_admin()


@pytest.fixture
def client_super_admin(fab):
    return fab.client_super_admin()
