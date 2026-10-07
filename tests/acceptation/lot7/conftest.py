"""Fixture du lot 7. ADAPTABLE par Gemini (jamais les test_*.py)."""
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[2]  # .../tests
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import pytest
from django_tenants.utils import schema_context

from fabriques_lot7 import FabriqueLot7


@pytest.fixture(autouse=True)
def _positionner_schema_tenant(db):
    """Maintient la connexion sur le schéma tenant demo pendant tout le test."""
    from apps.projets.services.tableau_de_bord_bons import vider_bons_test

    vider_bons_test()
    with schema_context("demo"):
        yield
    vider_bons_test()


@pytest.fixture
def fabrique(db):
    """Une fabrique par test, dans un tenant de test isolé (voir fabriques_lot7.py)."""
    return FabriqueLot7()
