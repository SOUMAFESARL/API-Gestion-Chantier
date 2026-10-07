"""E-11 (écriture) : pour écrire un montant, il faut projets.voir_montants ET le droit
d'écrire la ressource. Sinon 400 « champ non accepté », et rien n'est enregistré.

Précision [D] encodée ici : un montant NON NUL envoyé sans voir_montants est refusé ;
l'absence de la clé, ou la clé à null, est acceptée et ignorée (le front actuel peut
envoyer la clé à null).

Préfixes : test_carac_* = déjà vrai, à conserver ; test_regle_* = nouvelle règle.
"""

import pytest

ENTREPRISE = {"DG", "AD", "DO"}
CLE = "budget_initial_montant"
MONTANT = 1_000_000
DROIT_COMPLET = ["DG", "DO", "CP"]  # ecrire + voir_montants
ECRIT_SANS_VOIR = ["AD", "CT"]  # ecrire sans voir_montants
SANS_ECRIRE = ["DF", "VI"]  # pas de projets.ecrire
RESSOURCES = [
    "projet_modification",
    "lot_creation",
    "lot_modification",
    "activite_creation",
    "activite_modification",
]


def monde(fabrique):
    projet = fabrique.projet(budget=20_000_000)
    lot = fabrique.lot(projet, budget=10_000_000)
    activite = fabrique.activite(lot, budget=500_000)
    return projet, lot, activite


def acteur(fabrique, role, projet):
    utilisateur = fabrique.utilisateur(role)
    if role not in ENTREPRISE:
        # l'étiquette n'accorde aucun droit (E-06) : "VI" pour tous
        fabrique.affecter(projet, utilisateur, role_projet="VI")
    return fabrique.client(utilisateur)


def requete(fabrique, ressource, projet, lot, activite):
    """(méthode, url, corps sans montant, code de succès) pour une ressource."""
    table = {
        "projet_modification": ("patch", fabrique.url_projet(projet),
                                fabrique.payload_modification_projet(), 200),
        "lot_creation": ("post", fabrique.url_lots(projet), fabrique.payload_lot(), 201),
        "lot_modification": ("patch", fabrique.url_lot(projet, lot),
                             fabrique.payload_modification_lot(), 200),
        "activite_creation": ("post", fabrique.url_activites(lot),
                              fabrique.payload_activite(), 201),
        "activite_modification": ("patch", fabrique.url_activite(activite),
                                  fabrique.payload_modification_activite(), 200),
    }
    return table[ressource]


def envoyer(client, methode, url, corps):
    return getattr(client, methode)(url, corps, format="json")


# ---------------------------------------------------------------- droit complet
@pytest.mark.parametrize("ressource", RESSOURCES)
@pytest.mark.parametrize("role", DROIT_COMPLET)
def test_carac_montant_accepte_avec_les_deux_droits(fabrique, role, ressource):
    projet, lot, activite = monde(fabrique)
    client = acteur(fabrique, role, projet)
    methode, url, corps, succes = requete(fabrique, ressource, projet, lot, activite)
    reponse = envoyer(client, methode, url, {**corps, CLE: MONTANT})
    assert reponse.status_code == succes, reponse.content
    assert reponse.json()[CLE] == MONTANT


# ------------------------------------------------------ sans montant : tout passe
@pytest.mark.parametrize("ressource", RESSOURCES)
@pytest.mark.parametrize("role", DROIT_COMPLET + ECRIT_SANS_VOIR)
def test_carac_sans_montant_l_ecriture_reste_permise(fabrique, role, ressource):
    projet, lot, activite = monde(fabrique)
    client = acteur(fabrique, role, projet)
    methode, url, corps, succes = requete(fabrique, ressource, projet, lot, activite)
    reponse = envoyer(client, methode, url, corps)
    assert reponse.status_code == succes, reponse.content


@pytest.mark.parametrize("ressource", RESSOURCES)
@pytest.mark.parametrize("role", ECRIT_SANS_VOIR)
def test_carac_montant_null_est_accepte_et_ignore(fabrique, role, ressource):
    projet, lot, activite = monde(fabrique)
    client = acteur(fabrique, role, projet)
    methode, url, corps, succes = requete(fabrique, ressource, projet, lot, activite)
    reponse = envoyer(client, methode, url, {**corps, CLE: None})
    assert reponse.status_code == succes, reponse.content


# --------------------------------------------------- écriture sans voir_montants
@pytest.mark.parametrize("ressource", RESSOURCES)
@pytest.mark.parametrize("role", ECRIT_SANS_VOIR)
def test_regle_e11_montant_refuse_sans_voir_montants(fabrique, role, ressource):
    projet, lot, activite = monde(fabrique)
    client = acteur(fabrique, role, projet)
    methode, url, corps, _ = requete(fabrique, ressource, projet, lot, activite)
    reponse = envoyer(client, methode, url, {**corps, CLE: MONTANT})
    assert reponse.status_code == 400, reponse.content


@pytest.mark.parametrize("role", ECRIT_SANS_VOIR)
def test_regle_e11_refus_n_enregistre_rien_sur_un_projet(fabrique, role):
    projet, lot, activite = monde(fabrique)
    dg = fabrique.client(fabrique.utilisateur("DG"))
    avant = dg.get(fabrique.url_projet(projet)).json()
    client = acteur(fabrique, role, projet)
    corps = {**fabrique.payload_modification_projet(), CLE: MONTANT}
    reponse = client.patch(fabrique.url_projet(projet), corps, format="json")
    assert reponse.status_code == 400, reponse.content
    apres = dg.get(fabrique.url_projet(projet)).json()
    assert apres == avant  # ni le montant, ni les autres champs du même PATCH


@pytest.mark.parametrize("role", ECRIT_SANS_VOIR)
def test_regle_e11_refus_ne_cree_rien_pour_un_lot(fabrique, role):
    projet, lot, activite = monde(fabrique)
    dg = fabrique.client(fabrique.utilisateur("DG"))
    avant = len(_liste(dg.get(fabrique.url_lots(projet))))
    client = acteur(fabrique, role, projet)
    corps = {**fabrique.payload_lot(), CLE: MONTANT}
    reponse = client.post(fabrique.url_lots(projet), corps, format="json")
    assert reponse.status_code == 400, reponse.content
    assert len(_liste(dg.get(fabrique.url_lots(projet)))) == avant


def _liste(reponse):
    data = reponse.json()
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


# ------------------------------------------------------- sans droit d'écriture
@pytest.mark.parametrize("ressource", RESSOURCES)
@pytest.mark.parametrize("role", SANS_ECRIRE)
def test_carac_sans_droit_d_ecriture_refus_403(fabrique, role, ressource):
    projet, lot, activite = monde(fabrique)
    client = acteur(fabrique, role, projet)
    methode, url, corps, _ = requete(fabrique, ressource, projet, lot, activite)
    assert envoyer(client, methode, url, corps).status_code == 403
    assert envoyer(client, methode, url, {**corps, CLE: MONTANT}).status_code == 403


# --------------------------------------------------------- création d'un projet
@pytest.mark.parametrize("role", ["DG", "DO"])
def test_carac_creation_projet_avec_montant_par_dg_et_do(fabrique, role):
    client = fabrique.client(fabrique.utilisateur(role))
    avant = fabrique.nombre_projets()
    reponse = client.post(fabrique.url_projets(),
                          {**fabrique.payload_projet(), CLE: MONTANT}, format="json")
    assert reponse.status_code == 201, reponse.content
    assert reponse.json()[CLE] == MONTANT
    assert fabrique.nombre_projets() == avant + 1


@pytest.mark.parametrize("role", ["CP", "CT"])
def test_carac_creation_projet_refusee_sans_projets_creer(fabrique, role):
    client = fabrique.client(fabrique.utilisateur(role))
    avant = fabrique.nombre_projets()
    reponse = client.post(fabrique.url_projets(),
                          {**fabrique.payload_projet(), CLE: MONTANT}, format="json")
    assert reponse.status_code == 403, reponse.content
    assert fabrique.nombre_projets() == avant


def test_regle_e11_creation_projet_avec_montant_refusee_pour_l_ad(fabrique):
    client = fabrique.client(fabrique.utilisateur("AD"))
    avant = fabrique.nombre_projets()
    reponse = client.post(fabrique.url_projets(),
                          {**fabrique.payload_projet(), CLE: MONTANT}, format="json")
    assert reponse.status_code == 400, reponse.content
    assert fabrique.nombre_projets() == avant  # aucun projet à moitié créé


def test_carac_l_ad_cree_un_projet_sans_montant(fabrique):
    client = fabrique.client(fabrique.utilisateur("AD"))
    avant = fabrique.nombre_projets()
    reponse = client.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
    assert reponse.status_code == 201, reponse.content
    assert fabrique.nombre_projets() == avant + 1


def test_carac_l_ad_cree_un_projet_avec_montant_null(fabrique):
    client = fabrique.client(fabrique.utilisateur("AD"))
    reponse = client.post(fabrique.url_projets(),
                          {**fabrique.payload_projet(), CLE: None}, format="json")
    assert reponse.status_code == 201, reponse.content
