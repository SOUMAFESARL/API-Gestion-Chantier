"""[F-09] Invariance : Météo et Référentiel des villes ne changent pas avec la refonte des droits.

Tests de caractérisation : ils décrivent le comportement actuel (lot 9 clos) et doivent
passer tels quels. Le fournisseur météo externe est neutralisé ; aucun contrôle d'accès
n'est jamais patché.
"""
import datetime

import pytest

URL_METEO = "/api/v1/projets/meteo/"
URL_VILLES = "/api/v1/projets/referentiels/villes/"

pytestmark = [pytest.mark.carac, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def entreprise(fabriques):
    return fabriques.creer_entreprise(pays="CI", ville_siege="Abidjan")


def _client(fabriques, entreprise, profil):
    return fabriques.client_authentifie(fabriques.creer_utilisateur(entreprise, profil))


# --- Météo : localisation --------------------------------------------------------------

@pytest.mark.parametrize("profil", ["DG", "AD", "DF"])
def test_f09_siege_sans_parametre_utilise_la_ville_de_l_entreprise(profil, fabriques, entreprise):
    """[F-09] Rôle de siège, aucun paramètre : ville de l'entreprise, portée ENTREPRISE."""
    client = _client(fabriques, entreprise, profil)
    with fabriques.espion_fournisseur_meteo() as espion:
        reponse = client.get(URL_METEO)
    assert reponse.status_code == 200, reponse.content
    assert reponse.json()["portee"] == "ENTREPRISE"
    assert espion.appels[-1] == "Abidjan"


@pytest.mark.parametrize("profil", ["DG", "CHANTIER"])
def test_f09_parametre_ville_explicite_l_emporte(profil, fabriques, entreprise):
    """[F-09] Le paramètre `ville` est prioritaire, pour un rôle de siège comme de chantier."""
    client = _client(fabriques, entreprise, profil)
    with fabriques.espion_fournisseur_meteo() as espion:
        reponse = client.get(URL_METEO, {"ville": "Bouake"})
    assert reponse.status_code == 200, reponse.content
    assert espion.appels[-1] == "Bouake"


def test_f09_chantier_avec_projet_visible_utilise_la_ville_du_projet(fabriques, entreprise):
    """[F-09] Rôle de chantier affecté, `projet_id` visible : ville du chantier."""
    utilisateur = fabriques.creer_utilisateur(entreprise, "CHANTIER")
    projet = fabriques.creer_projet(entreprise, ville="Korhogo")
    fabriques.affecter(utilisateur, projet, debut=datetime.date(2026, 1, 5))
    client = fabriques.client_authentifie(utilisateur)
    with fabriques.espion_fournisseur_meteo() as espion:
        reponse = client.get(URL_METEO, {"projet_id": projet.id})
    assert reponse.status_code == 200, reponse.content
    assert espion.appels[-1] == "Korhogo"


def test_f09_chantier_sans_parametre_utilise_l_affectation_la_plus_recente(fabriques, entreprise):
    """[F-09] Rôle de chantier, aucun paramètre : ville de l'affectation la plus récente."""
    utilisateur = fabriques.creer_utilisateur(entreprise, "CHANTIER")
    ancien = fabriques.creer_projet(entreprise, ville="Yamoussoukro")
    recent = fabriques.creer_projet(entreprise, ville="San-Pedro")
    fabriques.affecter(utilisateur, ancien, debut=datetime.date(2026, 1, 5))
    fabriques.affecter(utilisateur, recent, debut=datetime.date(2026, 6, 1))
    client = fabriques.client_authentifie(utilisateur)
    with fabriques.espion_fournisseur_meteo() as espion:
        reponse = client.get(URL_METEO)
    assert reponse.status_code == 200, reponse.content
    assert espion.appels[-1] == "San-Pedro"


def test_f09_chantier_sans_affectation_retombe_sur_la_ville_de_l_entreprise(fabriques, entreprise):
    """[F-09] Rôle de chantier sans affectation : ville de l'entreprise par défaut."""
    client = _client(fabriques, entreprise, "CHANTIER")
    with fabriques.espion_fournisseur_meteo() as espion:
        reponse = client.get(URL_METEO)
    assert reponse.status_code == 200, reponse.content
    assert espion.appels[-1] == "Abidjan"


def test_f09_projet_non_visible_est_refuse_sans_appel_externe(fabriques, entreprise):
    """[F-09] `projet_id` d'un projet non visible : repli siège et le fournisseur n'est pas appelé pour ce projet."""
    projet = fabriques.creer_projet(entreprise, ville="Daloa")
    client = _client(fabriques, entreprise, "CHANTIER")
    with fabriques.espion_fournisseur_meteo() as espion:
        reponse = client.get(URL_METEO, {"projet_id": projet.id})
    assert reponse.status_code == 200, reponse.content
    assert reponse.json()["portee"] == "ENTREPRISE"
    assert "Daloa" not in espion.appels


# --- Météo : forme de la réponse --------------------------------------------------------

def test_f09_reponse_meteo_garde_ses_champs_structures(fabriques, entreprise):
    """[F-09] La réponse météo expose toujours condition, alerte, raison et portee."""
    client = _client(fabriques, entreprise, "DG")
    with fabriques.espion_fournisseur_meteo():
        corps = client.get(URL_METEO).json()
    for champ in ("condition", "alerte", "raison", "portee"):
        assert champ in corps, f"Champ {champ} disparu de la réponse météo"


# --- Référentiel des villes -------------------------------------------------------------

def test_f09_villes_par_defaut_est_le_pays_de_l_entreprise(fabriques, entreprise):
    """[F-09] Sans paramètre, les villes sont celles du pays de l'entreprise (CI), non vides."""
    client = _client(fabriques, entreprise, "DG")
    par_defaut = client.get(URL_VILLES)
    explicite = client.get(URL_VILLES, {"pays": "CI"})
    assert par_defaut.status_code == 200 and explicite.status_code == 200
    assert par_defaut.json(), "Référentiel des villes vide"
    assert par_defaut.json() == explicite.json()


def test_f09_villes_accessibles_sans_aucune_permission_projets(fabriques, entreprise):
    """[F-09] IsAuthenticated suffit : un rôle sans permission projets lit les villes."""
    client = _client(fabriques, entreprise, "AUCUNE_PERMISSION")
    assert client.get(URL_VILLES).status_code == 200


def test_f09_villes_et_meteo_restent_accessibles_module_projets_desactive(fabriques, entreprise):
    """[F-09] Module projets désactivé : villes et météo restent lisibles (aucun code de droit)."""
    fabriques.desactiver_module(entreprise, "projets")
    client = _client(fabriques, entreprise, "DG")
    assert client.get(URL_VILLES).status_code == 200
    with fabriques.espion_fournisseur_meteo():
        assert client.get(URL_METEO).status_code == 200


# --- Authentification -------------------------------------------------------------------

@pytest.mark.parametrize("url", [URL_METEO, URL_VILLES])
def test_f09_non_authentifie_est_refuse(url, fabriques, entreprise):
    """[F-09] Sans jeton, les deux routes répondent 401."""
    assert fabriques.client_anonyme(entreprise).get(url).status_code == 401
