"""
[E-13] Suppression définitive de ContexteCreationProjetView.
Vue, route, serializer et tests supprimés.
"""
import os
import re
from pathlib import Path

import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau

ROOT = Path(os.environ.get("BACKEND_ROOT", Path(__file__).resolve().parents[3]))
EXCLUS = {".git", "__pycache__", "node_modules", "venv", ".venv", "env", "migrations", "staticfiles", "tmp_kilo"}


def _fichiers_production():
    for dossier, sous, fichiers in os.walk(ROOT):
        rel = Path(dossier).relative_to(ROOT)
        sous[:] = [s for s in sous if s not in EXCLUS and not s.endswith(".egg-info")]
        if rel.parts[:1] in (("tests",), ("docs",)) or {"tests", "test"} & set(rel.parts):
            sous[:] = []
            continue
        for f in fichiers:
            if f.endswith(".py") and not f.startswith("test_") and f != "conftest.py":
                yield Path(dossier) / f


@NOUVEAU
def test_e13_route_contexte_creation_supprimee(fab):
    """[E-13] La route /api/v1/projets/contexte-creation/ renvoie 404 pour tout le monde (y compris le DG)."""
    dg = fab.acteur("DG")
    client = fab.client_pour(dg)
    r = client.get(fab.url_contexte_creation())
    assert r.status_code == 404, f"La route contexte-creation doit être supprimée (404), reçu {r.status_code}"


@NOUVEAU
def test_e13_statique_contexte_creation_absent():
    """[E-13] Zéro occurrence de ContexteCreationProjetView et ContexteCreationProjetSerializer en production."""
    termes = ("ContexteCreationProjetView", "ContexteCreationProjetSerializer")
    coupables = []
    for p in _fichiers_production():
        if p.name == "contexte_creation.py":
            coupables.append(f"Fichier encore présent: {p.relative_to(ROOT).as_posix()}")
        contenu = p.read_text(encoding="utf-8", errors="replace")
        for t in termes:
            if re.search(rf"\b{t}\b", contenu):
                coupables.append(f"{p.relative_to(ROOT).as_posix()}: mention de {t}")

    assert not coupables, "ContexteCreationProjet encore présent en production :\n" + "\n".join(coupables)
