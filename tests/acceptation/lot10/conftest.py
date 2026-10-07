"""Fixtures du lot 10.

Les tests statiques n'ont aucune dépendance Django. Les tests HTTP (F-09, G-02)
passent par `fabriques_lot10.py`, chargé par chemin pour ne pas dépendre de la
structure des paquets du dépôt.
"""
import importlib.util
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
DOSSIERS_IGNORES = {"__pycache__", ".venv", "venv", "node_modules", ".git", "staticfiles"}


def _fichiers_python(base: Path, exclure_migrations: bool):
    for chemin in sorted(base.rglob("*.py")):
        parties = set(chemin.relative_to(base).parts)
        if parties & DOSSIERS_IGNORES:
            continue
        if exclure_migrations and "migrations" in parties:
            continue
        yield chemin


def _rechercher(motif, base, *, exclure_migrations=False, exclure_fichiers=()):
    """Retourne les lignes `chemin:numéro: texte` où `motif` (regex) apparaît."""
    regex = re.compile(motif)
    exclus = {Path(p).resolve() for p in exclure_fichiers}
    trouvees = []
    for chemin in _fichiers_python(base, exclure_migrations):
        if chemin.resolve() in exclus:
            continue
        texte = chemin.read_text(encoding="utf-8", errors="ignore")
        for numero, ligne in enumerate(texte.splitlines(), start=1):
            if regex.search(ligne):
                trouvees.append(f"{chemin.relative_to(RACINE)}:{numero}: {ligne.strip()}")
    return trouvees


@pytest.fixture(scope="session")
def racine_depot() -> Path:
    return RACINE


@pytest.fixture(scope="session")
def rechercher():
    return _rechercher


@pytest.fixture(scope="session")
def lire_texte():
    def _lire(relatif: str) -> str:
        chemin = RACINE / relatif
        assert chemin.is_file(), f"Fichier attendu introuvable : {relatif}"
        return chemin.read_text(encoding="utf-8", errors="ignore")

    return _lire


@pytest.fixture(scope="session")
def fabriques():
    chemin = Path(__file__).with_name("fabriques_lot10.py")
    spec = importlib.util.spec_from_file_location("fabriques_lot10", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
