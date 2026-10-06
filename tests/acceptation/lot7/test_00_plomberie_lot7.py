"""Canari du lot 7 : ces tests prouvent que les fabriques sont saines.

Ils DOIVENT passer avant toute modification du code applicatif. S'ils échouent,
c'est la plomberie (fabriques_lot7.py, conftest.py) qui est fausse, pas la règle.
"""

import pytest

ROLES = ("DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI")


def liste(reponse):
    data = reponse.json()
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


@pytest.mark.parametrize("role", ROLES)
def test_carac_chaque_client_est_bien_son_utilisateur(fabrique, role):
    utilisateur = fabrique.utilisateur(role)
    reponse = fabrique.client(utilisateur).get("/api/v1/profil/")
    assert reponse.status_code == 200, reponse.content
    assert reponse.json().get("email") == utilisateur.email


def test_carac_anonyme_est_refuse(fabrique):
    assert fabrique.client().get("/api/v1/profil/").status_code == 401


def test_carac_urls_lecture_valides_pour_le_dg(fabrique):
    dg = fabrique.utilisateur("DG")
    client = fabrique.client(dg)
    projet = fabrique.projet(budget=10_000_000)
    lot = fabrique.lot(projet, budget=4_000_000)
    activite = fabrique.activite(lot, budget=1_000_000)
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


def test_carac_le_dg_lit_les_budgets(fabrique):
    dg = fabrique.utilisateur("DG")
    client = fabrique.client(dg)
    projet = fabrique.projet(budget=10_000_000)
    lot = fabrique.lot(projet, budget=4_000_000)
    activite = fabrique.activite(lot, budget=1_000_000)
    assert client.get(fabrique.url_projet(projet)).json()["budget_initial_montant"] == 10_000_000
    assert client.get(fabrique.url_lot(projet, lot)).json()["budget_initial_montant"] == 4_000_000
    assert client.get(fabrique.url_activite(activite)).json()["budget_initial_montant"] == 1_000_000


def test_carac_payloads_valides_pour_le_dg(fabrique):
    dg = fabrique.utilisateur("DG")
    client = fabrique.client(dg)
    projet = fabrique.projet(budget=20_000_000)
    lot = fabrique.lot(projet, budget=10_000_000)
    activite = fabrique.activite(lot, budget=500_000)

    r = client.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
    assert r.status_code == 201, r.content
    r = client.post(fabrique.url_lots(projet), fabrique.payload_lot(), format="json")
    assert r.status_code == 201, r.content
    r = client.post(fabrique.url_activites(lot), fabrique.payload_activite(), format="json")
    assert r.status_code == 201, r.content
    r = client.patch(fabrique.url_projet(projet), fabrique.payload_modification_projet(), format="json")
    assert r.status_code == 200, r.content
    r = client.patch(fabrique.url_lot(projet, lot), fabrique.payload_modification_lot(), format="json")
    assert r.status_code == 200, r.content
    r = client.patch(fabrique.url_activite(activite), fabrique.payload_modification_activite(), format="json")
    assert r.status_code == 200, r.content


def test_carac_dashboard_du_dg_a_la_forme_attendue(fabrique):
    dg = fabrique.utilisateur("DG")
    fabrique.projet(budget=10_000_000)
    data = fabrique.client(dg).get(fabrique.url_dashboard()).json()
    assert {"metriques", "projets", "bons_paiement_a_valider"} <= set(data)
    assert "budget_total_montant" in data["metriques"]
    assert "bons_a_signer_count" in data["metriques"]
    assert len(data["projets"]) >= 1
    assert "budget_initial_montant" in data["projets"][0]
