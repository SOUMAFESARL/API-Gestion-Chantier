"""
conftest du LOT 5 : VERROUILLÉ.
Toute dépendance aux noms réels du dépôt est dans tests/fabriques_lot5.py.
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
        "caracterisation: comportement qui DOIT déjà passer à la fin du lot 4 (dry-run)",
    )
    config.addinivalue_line(
        "markers",
        "nouveau: comportement que le lot 5 introduit (échoue avant le lot)",
    )


@pytest.fixture(autouse=True)
def _acces_base(db):
    yield


@pytest.fixture
def fab():
    import fabriques_lot5

    return fabriques_lot5
