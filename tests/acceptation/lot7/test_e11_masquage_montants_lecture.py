"""E-11 (lecture) : sans projets.voir_montants, AUCUN champ de montant dans la réponse.

Les clés sont absentes du JSON (ni null, ni 0). Les champs hors montants restent.
Préfixes : test_carac_* = comportement déjà vrai, à conserver (vert avant et après) ;
test_regle_* = nouvelle règle (rouge avant, vert après).
"""

import re

import pytest

ENTREPRISE = {"DG", "AD", "DO"}  # portée ENTREPRISE (règle D-07)
VOIENT = ["DG", "DO", "CP", "DF"]  # ont projets.voir_montants (annexe 1)
NE_VOIENT_PAS = ["AD", "CT", "CC", "BAI", "VI"]
CLE = "budget_initial_montant"
MOTIF_MONTANT = re.compile(r"(montant|budget|cout|prix)")


def liste(reponse):
    data = reponse.json()
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def cles(objet):
    """Toutes les clés d'un JSON, à tous les niveaux."""
    trouvees = set()
    if isinstance(objet, dict):
        for cle, valeur in objet.items():
            trouvees.add(cle)
            trouvees |= cles(valeur)
    elif isinstance(objet, list):
        for element in objet:
            trouvees |= cles(element)
    return trouvees


def monde(fabrique, role):
    projet = fabrique.projet(budget=10_000_000)
    lot = fabrique.lot(projet, budget=4_000_000)
    activite = fabrique.activite(lot, budget=1_000_000)
    utilisateur = fabrique.utilisateur(role)
    if role not in ENTREPRISE:
        fabrique.affecter(projet, utilisateur, role_projet="VI")
    return projet, lot, activite, fabrique.client(utilisateur)


def element(reponse, identifiant):
    for item in liste(reponse):
        if str(item.get("id")) == str(identifiant):
            return item
    raise AssertionError(f"élément {identifiant} absent de la liste")


# ------------------------------------------------------- ceux qui voient les montants
@pytest.mark.parametrize("role", VOIENT)
def test_carac_projet_avec_montant(fabrique, role):
    projet, _, _, client = monde(fabrique, role)
    detail = client.get(fabrique.url_projet(projet))
    assert detail.status_code == 200, detail.content
    assert detail.json()[CLE] == 10_000_000
    liste_projets = client.get(fabrique.url_projets())
    assert liste_projets.status_code == 200, liste_projets.content
    assert element(liste_projets, projet.id)[CLE] == 10_000_000


@pytest.mark.parametrize("role", VOIENT)
def test_carac_lot_et_activite_avec_montant(fabrique, role):
    projet, lot, activite, client = monde(fabrique, role)
    r = client.get(fabrique.url_lot(projet, lot))
    assert r.status_code == 200, r.content
    assert r.json()[CLE] == 4_000_000
    r = client.get(fabrique.url_lots(projet))
    assert element(r, lot.id)[CLE] == 4_000_000
    r = client.get(fabrique.url_activite(activite))
    assert r.status_code == 200, r.content
    assert r.json()[CLE] == 1_000_000
    r = client.get(fabrique.url_activites(lot))
    assert element(r, activite.id)[CLE] == 1_000_000


@pytest.mark.parametrize("role", VOIENT)
def test_carac_dashboard_avec_montants(fabrique, role):
    _, _, _, client = monde(fabrique, role)
    reponse = client.get(fabrique.url_dashboard())
    assert reponse.status_code == 200, reponse.content
    data = reponse.json()
    assert data["metriques"]["budget_total_montant"] >= 10_000_000
    assert len(data["projets"]) >= 1
    for item in data["projets"]:
        assert CLE in item


# ------------------------------------------------- ceux qui ne voient pas les montants
@pytest.mark.parametrize("role", NE_VOIENT_PAS)
def test_regle_e11_projet_sans_montant(fabrique, role):
    projet, _, _, client = monde(fabrique, role)
    detail = client.get(fabrique.url_projet(projet))
    assert detail.status_code == 200, detail.content
    assert CLE not in cles(detail.json())
    # les champs hors montants restent présents
    assert str(detail.json()["id"]) == str(projet.id)
    assert "statut" in detail.json()
    liste_projets = client.get(fabrique.url_projets())
    assert liste_projets.status_code == 200, liste_projets.content
    element(liste_projets, projet.id)  # le projet est bien dans la liste
    assert CLE not in cles(liste_projets.json())


@pytest.mark.parametrize("role", NE_VOIENT_PAS)
def test_regle_e11_lot_sans_montant(fabrique, role):
    projet, lot, _, client = monde(fabrique, role)
    r = client.get(fabrique.url_lot(projet, lot))
    assert r.status_code == 200, r.content
    assert CLE not in cles(r.json())
    assert str(r.json()["id"]) == str(lot.id)
    r = client.get(fabrique.url_lots(projet))
    assert r.status_code == 200, r.content
    element(r, lot.id)
    assert CLE not in cles(r.json())


@pytest.mark.parametrize("role", NE_VOIENT_PAS)
def test_regle_e11_activite_sans_montant(fabrique, role):
    _, lot, activite, client = monde(fabrique, role)
    r = client.get(fabrique.url_activite(activite))
    assert r.status_code == 200, r.content
    assert CLE not in cles(r.json())
    assert str(r.json()["id"]) == str(activite.id)
    r = client.get(fabrique.url_activites(lot))
    assert r.status_code == 200, r.content
    element(r, activite.id)
    assert CLE not in cles(r.json())


# ----------------------------------------------------------------------- dashboard
@pytest.mark.parametrize("role", ["AD", "CT"])
def test_regle_e11_dashboard_sans_montant(fabrique, role):
    _, _, _, client = monde(fabrique, role)
    reponse = client.get(fabrique.url_dashboard())
    assert reponse.status_code == 200, reponse.content
    data = reponse.json()
    assert "budget_total_montant" not in data["metriques"]
    assert len(data["projets"]) >= 1
    for item in data["projets"]:
        assert CLE not in item


@pytest.mark.parametrize("role", ["DG", "AD", "CT", "CP"])
def test_carac_dashboard_garde_les_champs_non_monetaires(fabrique, role):
    _, _, _, client = monde(fabrique, role)
    data = client.get(fabrique.url_dashboard()).json()
    assert "bons_a_signer_count" in data["metriques"]
    assert "bons_paiement_a_valider" in data


def test_carac_montant_bon_paiement_visible_pour_le_dg(fabrique):
    projet, _, _, client = monde(fabrique, "DG")
    fabrique.bon_paiement(projet, montant=250_000)
    items = client.get(fabrique.url_dashboard()).json()["bons_paiement_a_valider"]
    assert len(items) >= 1
    assert "montant" in items[0]


def test_regle_e11_montant_bon_paiement_masque_pour_l_ad(fabrique):
    projet, _, _, client = monde(fabrique, "AD")
    fabrique.bon_paiement(projet, montant=250_000)
    items = client.get(fabrique.url_dashboard()).json()["bons_paiement_a_valider"]
    assert len(items) >= 1
    assert "montant" not in cles(items)


# ------------------------------------------------------------ filet : omission possible
@pytest.mark.parametrize("role", ["AD", "CT"])
def test_regle_e11_filet_aucune_cle_de_montant(fabrique, role):
    """Aucune clé évoquant un montant dans AUCUNE ressource, y compris les statistiques."""
    projet, lot, activite, client = monde(fabrique, role)
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
        fautives = sorted(c for c in cles(reponse.json()) if MOTIF_MONTANT.search(c))
        assert not fautives, (url, fautives)
