"""Tests statiques du lot 8 (non-régression et extinction de la dette D-08).

Vérifie l'éradication complète de RoleRequis, des constantes de rôles obsolètes,
et l'absence de boucle sur Entreprise.objects dans le service d'authentification.
"""

import re
import pytest
from pathlib import Path

_RACINE = Path(__file__).resolve().parents[3]  # racine du dépôt API


@pytest.mark.regle
def test_statique_zero_role_requis_hors_core():
    """[D-08 / L8-7] RoleRequis a disparu entièrement : zéro occurrence hors apps/core/permissions.py."""
    motif = re.compile(r"\bRoleRequis\b")
    fichiers = list(_RACINE.glob("apps/**/*.py"))
    occurrences = []

    for f in fichiers:
        if "apps/core/permissions.py" in str(f).replace("\\", "/"):
            continue
        texte = f.read_text(encoding="utf-8")
        if motif.search(texte):
            rel = str(f.relative_to(_RACINE)).replace("\\", "/")
            occurrences.append(rel)

    assert not occurrences, (
        "RoleRequis doit avoir entièrement disparu du code applicatif :\n"
        + "\n".join(occurrences)
    )


@pytest.mark.carac
def test_statique_zero_anciennes_gardes_hors_core():
    """[D-08] PermissionModule et MembreDuProjet : zéro occurrence hors apps/core/permissions.py."""
    motif = re.compile(r"\b(PermissionModule|MembreDuProjet)\b")
    fichiers = list(_RACINE.glob("apps/**/*.py"))
    occurrences = []

    for f in fichiers:
        if "apps/core/permissions.py" in str(f).replace("\\", "/"):
            continue
        texte = f.read_text(encoding="utf-8")
        if motif.search(texte):
            rel = str(f.relative_to(_RACINE)).replace("\\", "/")
            occurrences.append(rel)

    assert not occurrences, (
        "Anciennes gardes trouvées hors de apps/core/permissions.py :\n"
        + "\n".join(occurrences)
    )


@pytest.mark.regle
def test_statique_zero_constantes_roles_facturation():
    """[L8-7] Les constantes mortes ROLES_FACTURATION et équivalents sont absentes de apps/billing/."""
    motif = re.compile(r"\bROLES_FACTURATION\b")
    fichiers = list((_RACINE / "apps" / "billing").glob("**/*.py"))
    occurrences = []

    for f in fichiers:
        texte = f.read_text(encoding="utf-8")
        if motif.search(texte):
            rel = str(f.relative_to(_RACINE)).replace("\\", "/")
            occurrences.append(rel)

    assert not occurrences, (
        "Constante ROLES_FACTURATION trouvée dans billing :\n"
        + "\n".join(occurrences)
    )


@pytest.mark.regle
def test_statique_authentification_sans_boucle_sur_entreprises():
    """[C-03] Aucune occurrence de Entreprise.objects dans le service d'authentification (connexion directe sans boucle)."""
    fichier_auth = _RACINE / "apps" / "accounts" / "services" / "authentification.py"
    assert fichier_auth.exists()
    texte = fichier_auth.read_text(encoding="utf-8")

    assert "Entreprise.objects" not in texte, (
        "Le service d'authentification ne doit plus parcourir Entreprise.objects pour chercher l'utilisateur."
    )
