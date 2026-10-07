"""[CLOTURE] Contrôles statiques de sortie de la refonte des droits."""
import re

import pytest

# (identifiant, motif, exclure_migrations, fichiers_exclus relatifs à la racine)
CONTROLES_APPS = [
    ("niveau_max", r"\bniveau_max\b", True, ()),
    ("PermissionModule", r"\bPermissionModule\b", False, ("apps/core/permissions.py",)),
    ("RoleRequis", r"\bRoleRequis\b", False, ("apps/core/permissions.py",)),
    ("ProjetRoleModuleOverride", r"\bProjetRoleModuleOverride\b", True, ()),
    ("ContexteCreationProjetView", r"\bContexteCreationProjetView\b", False, ()),
    ("ROLES_DIRECTION", r"\bROLES_DIRECTION\b", False, ()),
    ("ROLES_GESTION_CHANTIER", r"\bROLES_GESTION_CHANTIER\b", False, ()),
    ("ROLES_VALIDATION_CHANTIER", r"\bROLES_VALIDATION_CHANTIER\b", False, ()),
]

TITRES_RAPPORT = {
    "synthèse": r"synth[eè]se",
    "périmètre": r"p[eé]rim[eè]tre",
    "chronologie": r"chronologie",
    "résultats des tests": r"r[eé]sultats?\s+des\s+tests",
    "contrôles statiques": r"contr[oô]les?\s+statiques",
    "écarts et arbitrages": r"[eé]carts?",
    "risques résiduels": r"risques?",
    "compatibilité frontend": r"compatibilit[eé]|front",
    "déploiement et retour arrière": r"d[eé]ploiement",
    "certification": r"certification",
}


@pytest.mark.carac
@pytest.mark.parametrize(
    "motif,exclure_migrations,exclus",
    [c[1:] for c in CONTROLES_APPS],
    ids=[c[0] for c in CONTROLES_APPS],
)
def test_cloture_zero_occurrence_dans_apps(motif, exclure_migrations, exclus, racine_depot, rechercher):
    """[CLOTURE] Aucune occurrence du motif interdit dans apps/ (grep de sortie de refonte)."""
    trouvees = rechercher(
        motif,
        racine_depot / "apps",
        exclure_migrations=exclure_migrations,
        exclure_fichiers=[racine_depot / e for e in exclus],
    )
    assert not trouvees, "Anti-pattern réapparu :\n" + "\n".join(trouvees)


@pytest.mark.carac
def test_cloture_voir_tous_absent_du_registre(lire_texte):
    """[CLOTURE] La permission projets.voir_tous n'existe plus dans le registre des permissions."""
    texte = lire_texte("apps/core/registre_permissions.py")
    assert "projets.voir_tous" not in texte


@pytest.mark.carac
@pytest.mark.django_db
def test_cloture_aucune_derive_de_migrations():
    """[CLOTURE] Les modèles et les migrations sont synchrones (aucune migration manquante)."""
    from django.core.management import call_command

    try:
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)
    except SystemExit as sortie:
        pytest.fail(f"Migrations manquantes (code de sortie {sortie.code})")


@pytest.mark.regle
def test_cloture_rapport_final_present(lire_texte):
    """[CLOTURE] docs/refonte/rapport-final.md existe et n'est pas le gabarit brut."""
    texte = lire_texte("docs/refonte/rapport-final.md")
    assert len(texte.strip().splitlines()) >= 40, "Rapport final trop court"
    assert "À COMPLÉTER" not in texte and "A_COMPLETER" not in texte, "Gabarit non rempli"


@pytest.mark.regle
@pytest.mark.parametrize("rubrique", list(TITRES_RAPPORT))
def test_cloture_rapport_final_rubrique(rubrique, lire_texte):
    """[CLOTURE] Le rapport final a une rubrique « {rubrique} »."""
    titres = re.findall(r"(?m)^#{1,4}\s+(.*)$", lire_texte("docs/refonte/rapport-final.md"))
    motif = re.compile(TITRES_RAPPORT[rubrique], re.IGNORECASE)
    assert any(motif.search(t) for t in titres), f"Rubrique « {rubrique} » absente"


@pytest.mark.regle
@pytest.mark.parametrize("numero", range(1, 11))
def test_cloture_rapport_cite_le_tag_de_chaque_lot(numero, lire_texte):
    """[CLOTURE] Le rapport final cite le tag lot{numero}-ok."""
    assert f"lot{numero}-ok" in lire_texte("docs/refonte/rapport-final.md")


@pytest.mark.regle
def test_cloture_rapport_cite_le_tag_souverain(lire_texte):
    """[CLOTURE] Le rapport final cite le tag souverain refonte-droits-ok."""
    assert "refonte-droits-ok" in lire_texte("docs/refonte/rapport-final.md")
