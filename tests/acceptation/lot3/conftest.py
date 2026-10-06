"""
conftest du LOT 3 : VERROUILLÉ. Gemini ne le modifie jamais.
Toute dépendance aux noms réels du dépôt est dans tests/fabriques_lot3.py.
"""
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[2]  # .../tests
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "caracterisation: décrit un comportement qui DOIT déjà passer à la fin du lot 2 (dry-run)",
    )
    config.addinivalue_line(
        "markers",
        "nouveau: décrit un comportement que le lot 3 introduit (échoue avant le lot)",
    )


@pytest.fixture(autouse=True)
def _acces_base(db):
    yield


@pytest.fixture
def fab():
    import fabriques_lot3

    return fabriques_lot3


@pytest.fixture
def projet(fab):
    return fab.creer_projet()
