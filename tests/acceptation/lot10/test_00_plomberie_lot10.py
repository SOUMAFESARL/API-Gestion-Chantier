"""[PLOMBERIE] Prérequis du lot 10 : dépôt, tag lot9-ok, verrous des lots précédents."""
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]

FICHIERS_REQUIS_DEPOT = [
    "docs/refonte/cahier-regles.md",
    "docs/refonte/plan-par-lots.md",
    "docs/notes-changement-api.md",
    "docs/api-projets-statuts.md",
    "apps/billing/views/facture.py",
    "apps/billing/views/expiration.py",
    "apps/projets/views/meteo.py",
    "apps/core/registre_permissions.py",
    "tests/acceptation/lot9/verifier_verrouillage.py",
]

FICHIERS_LOT10 = [
    "conftest.py",
    "test_00_plomberie_lot10.py",
    "test_f09_meteo_villes_invariance.py",
    "test_f10_nettoyage_docstrings_constantes.py",
    "test_g02_compatibilite_contrat_front.py",
    "test_g03_notes_changement_api.py",
    "test_statiques_cloture_refonte.py",
    "fabriques_lot10.py",
    "verifier_verrouillage.py",
]

LOTS_AVEC_VERROU = [
    n for n in range(1, 10)
    if (RACINE / f"tests/acceptation/lot{n}/verifier_verrouillage.py").is_file()
]


@pytest.mark.carac
@pytest.mark.parametrize("relatif", FICHIERS_REQUIS_DEPOT)
def test_depot_fichier_requis_present(relatif):
    """[PLOMBERIE] Les fichiers que le lot 10 contrôle existent dans le dépôt."""
    assert (RACINE / relatif).is_file(), f"Introuvable : {relatif}"


@pytest.mark.carac
@pytest.mark.parametrize("nom", FICHIERS_LOT10)
def test_lot10_fichier_du_lot_present(nom):
    """[PLOMBERIE] Les fichiers du lot 10 prévus par le cadrage sont tous présents."""
    assert (Path(__file__).parent / nom).is_file(), f"Absent du lot 10 : {nom}"


@pytest.mark.carac
def test_tag_lot9_ok_sur_le_commit_attendu():
    """[PLOMBERIE] Le tag lot9-ok pointe sur le commit 2797393."""
    if not (RACINE / ".git").exists():
        pytest.skip("dépôt git absent de l'environnement de test")
    sortie = subprocess.run(
        ["git", "rev-parse", "lot9-ok^{commit}"],
        cwd=RACINE, capture_output=True, text=True, timeout=30,
    )
    assert sortie.returncode == 0, f"Tag lot9-ok introuvable : {sortie.stderr.strip()}"
    assert sortie.stdout.strip().startswith("2797393"), sortie.stdout.strip()


@pytest.mark.carac
@pytest.mark.parametrize("numero", LOTS_AVEC_VERROU)
def test_verrou_des_lots_precedents_intact(numero):
    """[PLOMBERIE] Les fichiers de tests gelés du lot {numero} n'ont pas été modifiés."""
    script = RACINE / f"tests/acceptation/lot{numero}/verifier_verrouillage.py"
    sortie = subprocess.run(
        [sys.executable, str(script)],
        cwd=RACINE, capture_output=True, text=True, timeout=180,
    )
    assert sortie.returncode == 0, (sortie.stdout + sortie.stderr)[-1500:]
