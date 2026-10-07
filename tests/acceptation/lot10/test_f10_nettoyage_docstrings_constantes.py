"""[F-10] Nettoyage : constantes mortes, docstrings « DF », paragraphes « Apprentissage »."""
import ast
import re

import pytest

CONSTANTES_MORTES = ("ROLES_DIRECTION", "ROLES_GESTION_CHANTIER", "ROLES_VALIDATION_CHANTIER")
VUES_FACTURATION = ("apps/billing/views/facture.py", "apps/billing/views/expiration.py")


def _chaines(texte: str):
    """Toutes les chaînes littérales du fichier (docstrings et descriptions OpenAPI comprises)."""
    arbre = ast.parse(texte)
    return [
        n.value for n in ast.walk(arbre)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


@pytest.mark.carac
@pytest.mark.parametrize("nom", CONSTANTES_MORTES)
def test_f10_constante_morte_absente(nom, racine_depot, rechercher):
    """[F-10] La constante morte `{nom}` n'existe plus dans apps/ ni config/."""
    trouvees = []
    for dossier in ("apps", "config"):
        base = racine_depot / dossier
        if base.is_dir():
            trouvees += rechercher(rf"\b{nom}\b", base)
    assert not trouvees, "Constante morte réapparue :\n" + "\n".join(trouvees)


@pytest.mark.regle
@pytest.mark.parametrize("relatif", VUES_FACTURATION)
def test_f10_aucune_mention_df_dans_les_descriptions(relatif, lire_texte):
    """[F-10] Aucune chaîne de {relatif} (docstring ou description OpenAPI) ne cite « DF »."""
    fautives = [c for c in _chaines(lire_texte(relatif)) if re.search(r"\bDF\b", c)]
    assert not fautives, "Mention de DF à retirer :\n" + "\n".join(c[:160] for c in fautives)


@pytest.mark.carac
@pytest.mark.parametrize("relatif", VUES_FACTURATION)
def test_f10_descriptions_citent_toujours_dg_et_ad(relatif, lire_texte):
    """[F-10] La correction conserve la mention des rôles DG et AD dans {relatif}."""
    ensemble = "\n".join(_chaines(lire_texte(relatif)))
    assert re.search(r"\bDG\b", ensemble), "DG n'est plus cité"
    assert re.search(r"\bAD\b", ensemble), "AD n'est plus cité"


@pytest.mark.carac
def test_f10_paragraphe_apprentissage_absent(lire_texte):
    """[F-10] docs/api-projets-statuts.md ne contient aucun paragraphe « Apprentissage »."""
    texte = lire_texte("docs/api-projets-statuts.md")
    lignes = [l for l in texte.splitlines() if re.search(r"(?i)apprentissage", l)]
    assert not lignes, "Résidu « Apprentissage » :\n" + "\n".join(lignes)
