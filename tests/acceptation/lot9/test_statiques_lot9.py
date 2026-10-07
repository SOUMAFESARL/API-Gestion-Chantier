"""Tests statiques du lot 9 (Vérification du code mort et des interdits de refonte).

1. La logique de catalogue.py qui auto-injectait les permissions aux rôles DG et AD a disparu.
2. appliquer_modeles_roles n'est appelée dans aucune vue ni service d'exécution.
"""

import ast
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]  # racine API-Gestion-Chantier


@pytest.mark.regle
def test_statique_fonction_catalogue_ajoute_aux_roles_supprimee():
    """[Statique A-05 / R2] La fonction propager_creation_permission ne doit plus ajouter de permissions aux rôles."""
    cat_file = ROOT / "apps" / "platform_admin" / "services" / "catalogue.py"
    assert cat_file.exists()
    content = cat_file.read_text(encoding="utf-8")

    # On vérifie que le bloc d'auto-attribution aux rôles a été purgé de propager_creation_permission
    assert "roles_direction = Role.objects.filter" not in content, (
        "Le bloc 'roles_direction = Role.objects.filter' doit être supprimé de catalogue.py selon la règle A-05."
    )


@pytest.mark.regle
def test_statique_appliquer_modeles_roles_hors_vues_et_services():
    """[Statique A-13] appliquer_modeles_roles ne doit être référencée dans aucune vue ni service d'exécution sur tenant existant."""
    apps_dir = ROOT / "apps"
    motifs_interdits = re.compile(r"appliquer_modeles_roles\(")

    fichiers_fautes = []
    for py_file in apps_dir.rglob("*.py"):
        if "migrations" in py_file.parts or "tests" in py_file.parts:
            continue
        # Ne pas vérifier la déclaration de la fonction elle-même dans accounts/services/roles.py
        if py_file.name == "roles.py" and "services" in py_file.parts:
            continue
        try:
            texte = py_file.read_text(encoding="utf-8")
            if motifs_interdits.search(texte):
                fichiers_fautes.append(str(py_file.relative_to(ROOT)))
        except Exception:
            pass

    assert len(fichiers_fautes) == 0, f"Appels interdits à appliquer_modeles_roles trouvés dans : {fichiers_fautes}"
