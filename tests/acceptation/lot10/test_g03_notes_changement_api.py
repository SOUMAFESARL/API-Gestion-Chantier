"""[G-03] docs/notes-changement-api.md : complétude des sections Lot 1 à Lot 10.

Format exigé pour chaque lot : un titre commençant par `Lot N` (niveau 1 à 3),
puis cinq rubriques (titre contenant le mot-clé) ; écrire « Aucun » si vide.
"""
import re

import pytest

# Règles couvertes par lot. Lot 8 : À RENSEIGNER depuis la fiche du lot 8 de
# docs/refonte/plan-par-lots.md (le test test_g03_regles_lot8_renseignees échoue tant que c'est vide).
REGLES_PAR_LOT = {
    8: ("C-01", "C-02", "C-03", "C-04", "C-05", "F-03", "F-04", "F-05", "F-06", "F-07", "F-08"),
    9: ("A-05", "A-06", "A-07", "A-08", "A-09", "A-10", "A-11", "A-14", "H-01", "H-02"),
    10: ("F-09", "F-10", "G-02", "G-03"),
}

RUBRIQUES = {
    "refus HTTP": r"refus",
    "codes d'erreur": r"codes?\s+d.erreur",
    "routes": r"route",
    "impact frontend": r"front",
    "règles couvertes": r"r[eè]gles?\s+couvertes",
}

TITRE_LOT = re.compile(r"(?im)^(#{1,3})\s*lot\s*(\d+)\b.*$")
TITRE_QUELCONQUE = re.compile(r"(?m)^#{1,6}\s+(.*)$")


def _sections(texte):
    """{numero_lot: texte de la section}, une section s'arrête au titre de lot suivant."""
    reperes = [(int(m.group(2)), m.start()) for m in TITRE_LOT.finditer(texte)]
    sections = {}
    for i, (numero, debut) in enumerate(reperes):
        fin = reperes[i + 1][1] if i + 1 < len(reperes) else len(texte)
        sections[numero] = texte[debut:fin]
    return sections


@pytest.fixture(scope="module")
def sections(lire_texte):
    return _sections(lire_texte("docs/notes-changement-api.md"))


@pytest.mark.carac
@pytest.mark.parametrize("numero", range(1, 8))
def test_g03_sections_lots_1_a_7_conservees(numero, sections):
    """[G-03] Les sections des lots 1 à 7 sont toujours présentes et non vides."""
    assert numero in sections, f"Section « Lot {numero} » absente"
    assert len(sections[numero].strip().splitlines()) >= 3


@pytest.mark.carac
def test_g03_code_projet_clos_documente(sections):
    """[G-03] Le refus 409 `projet_clos` (lot 6) est documenté dans les notes."""
    assert "projet_clos" in "\n".join(sections.values())


@pytest.mark.regle
@pytest.mark.parametrize("numero", (8, 9, 10))
def test_g03_section_presente_et_substantielle(numero, sections):
    """[G-03] La section « Lot {numero} » existe et contient au moins 8 lignes non vides."""
    assert numero in sections, f"Section « Lot {numero} » absente"
    lignes = [l for l in sections[numero].splitlines() if l.strip()]
    assert len(lignes) >= 8, f"Section Lot {numero} trop courte ({len(lignes)} lignes)"


@pytest.mark.regle
@pytest.mark.parametrize("numero", (8, 9, 10))
@pytest.mark.parametrize("rubrique", list(RUBRIQUES))
def test_g03_rubrique_presente(numero, rubrique, sections):
    """[G-03] Chaque section Lot 8, 9, 10 a un titre de rubrique « {rubrique} »."""
    assert numero in sections, f"Section « Lot {numero} » absente"
    titres = TITRE_QUELCONQUE.findall(sections[numero])[1:]  # [0] = titre du lot
    motif = re.compile(RUBRIQUES[rubrique], re.IGNORECASE)
    assert any(motif.search(t) for t in titres), f"Rubrique « {rubrique} » absente du Lot {numero}"


@pytest.mark.regle
def test_g03_regles_lot8_renseignees():
    """[G-03] La liste des règles du lot 8 a été renseignée dans ce fichier de test."""
    assert REGLES_PAR_LOT[8], "Renseigner REGLES_PAR_LOT[8] depuis plan-par-lots.md (fiche du lot 8)"


@pytest.mark.regle
@pytest.mark.parametrize("numero", (8, 9, 10))
def test_g03_toutes_les_regles_du_lot_sont_citees(numero, sections):
    """[G-03] Chaque règle couverte par le lot {numero} est citée dans sa section."""
    assert numero in sections, f"Section « Lot {numero} » absente"
    manquantes = [r for r in REGLES_PAR_LOT[numero] if r not in sections[numero]]
    assert not manquantes, f"Règles non citées dans le Lot {numero} : {manquantes}"
