"""E-12 : les champs sans source réelle disparaissent de l'API, pour TOUS les rôles
(le DG compris), dans toutes les ressources, et du code applicatif.

Tous les tests de ce fichier sont des règles nouvelles : rouges avant, verts après.
"""

import re
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parents[3]
ENTREPRISE = {"DG", "AD", "DO"}
INTERDITS = (
    "budget_consomme_montant",
    "budget_engage_montant",
    "bons_a_signer_montant",
    "budget_activites_montant",
)
ROLES = ["DG", "DO", "CP", "DF", "AD", "CT"]


def cles(objet):
    trouvees = set()
    if isinstance(objet, dict):
        for cle, valeur in objet.items():
            trouvees.add(cle)
            trouvees |= cles(valeur)
    elif isinstance(objet, list):
        for element in objet:
            trouvees |= cles(element)
    return trouvees


@pytest.mark.parametrize("role", ROLES)
def test_regle_e12_aucune_reponse_ne_contient_les_champs_retires(fabrique, role):
    projet = fabrique.projet(budget=10_000_000)
    lot = fabrique.lot(projet, budget=4_000_000)
    activite = fabrique.activite(lot, budget=1_000_000)
    utilisateur = fabrique.utilisateur(role)
    if role not in ENTREPRISE:
        fabrique.affecter(projet, utilisateur, role_projet="VI")
    client = fabrique.client(utilisateur)
    urls = [
        fabrique.url_projets(),
        fabrique.url_projet(projet),
        fabrique.url_lots(projet),
        fabrique.url_lot(projet, lot),
        fabrique.url_activites(lot),
        fabrique.url_activite(activite),
        fabrique.url_statistiques(projet),
        fabrique.url_dashboard(),
    ]
    for url in urls:
        reponse = client.get(url)
        assert reponse.status_code == 200, (url, reponse.content)
        presentes = sorted(set(INTERDITS) & cles(reponse.json()))
        assert not presentes, (url, presentes)


@pytest.mark.parametrize("role", ["DG", "CP"])
def test_regle_e12_les_reponses_d_ecriture_ne_contiennent_pas_les_champs(fabrique, role):
    projet = fabrique.projet(budget=20_000_000)
    lot = fabrique.lot(projet, budget=10_000_000)
    utilisateur = fabrique.utilisateur(role)
    if role not in ENTREPRISE:
        fabrique.affecter(projet, utilisateur, role_projet="VI")
    client = fabrique.client(utilisateur)
    reponse = client.patch(fabrique.url_projet(projet),
                           fabrique.payload_modification_projet(), format="json")
    assert reponse.status_code == 200, reponse.content
    assert not (set(INTERDITS) & cles(reponse.json()))
    reponse = client.post(fabrique.url_lots(projet), fabrique.payload_lot(), format="json")
    assert reponse.status_code == 201, reponse.content
    assert not (set(INTERDITS) & cles(reponse.json()))


def sources_applicatives():
    """Fichiers Python applicatifs : ni migrations, ni tests, ni caches."""
    for racine in (DEPOT / "apps", DEPOT / "scripts"):
        if not racine.exists():
            continue
        for fichier in racine.rglob("*.py"):
            if set(fichier.parts) & {"migrations", "tests", "__pycache__"}:
                continue
            if fichier.name.startswith("test_") or fichier.name == "conftest.py":
                continue
            yield fichier


def test_regle_e12_les_champs_retires_n_existent_plus_dans_le_code():
    motif = re.compile("|".join(INTERDITS))
    trouves = []
    for fichier in sources_applicatives():
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if motif.search(ligne):
                trouves.append(f"{fichier.relative_to(DEPOT)}:{numero}")
    assert not trouves, trouves


def test_regle_e12_la_valeur_inventee_de_22_5_pourcent_a_disparu():
    trouves = []
    for fichier in sources_applicatives():
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b0\.225\b|\b22[.,]5\s*%", ligne):
                trouves.append(f"{fichier.relative_to(DEPOT)}:{numero}")
    assert not trouves, trouves


def test_regle_e12_les_notes_de_changement_api_documentent_le_retrait():
    """G-03 : le retrait et le masquage sont notés pour l'équipe front."""
    candidats = [
        DEPOT / "docs" / "notes-changement-api.md",
        DEPOT / "docs" / "refonte" / "notes-changement-api.md",
    ]
    existants = [c for c in candidats if c.exists()]
    assert existants, "notes-changement-api.md introuvable (docs/ ou docs/refonte/)"
    texte = existants[0].read_text(encoding="utf-8")
    for champ in INTERDITS:
        assert champ in texte, champ
    assert "voir_montants" in texte
