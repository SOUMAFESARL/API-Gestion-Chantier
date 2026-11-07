"""Couche 3 de l'isolation — chaque route, appelée par A sur ce qui appartient à B (D9, §4.3).

Le compte appelant est le **fondateur de A** (DG) : le compte le plus large d'une entreprise.
S'il ne franchit pas la frontière, un compte moins doté ne la franchit pas non plus par le même
chemin.

Pour chaque route qui désigne une ligne, et pour chaque méthode qu'elle sert :

1. la réponse est 403, 404 ou 405 — jamais un succès, jamais une erreur du serveur ;
2. aucun identifiant d'une ligne de B, aucune adresse de B, n'apparaît dans le corps ;
3. **les lignes de B sont intactes** après l'appel (témoin : nombre et empreinte, table par
   table) — un refus qui aurait écrit avant de refuser ne passe pas.

Pour chaque route sans identifiant (les listes), A l'appelle, y compris avec les identifiants de
B en paramètres de filtre (`?projet=<B>`) : aucune ligne de B dans le corps.

Le **contrôle positif** dit que la suite éprouve bien quelque chose : B, sur ses propres
identifiants, obtient un succès en lecture. Sans lui, un 404 rendu à A pourrait n'être qu'une
route mal désignée.
"""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import temoin
from django.test import Client
from outils_etancheite import (
    CONTROLE_SANS_OBJET,
    CORPS,
    EXCLUSIONS,
    PARAMETRES_PLATEFORME,
    REFUS_ATYPIQUES,
    VALEURS_FIXES,
    cible,
    toutes_les_routes,
)

pytestmark = pytest.mark.django_db

ROUTES = [r for r in toutes_les_routes() if r.gabarit not in EXCLUSIONS]
AVEC_IDENTIFIANT = [r for r in ROUTES if r.identifiants]
SANS_IDENTIFIANT = [r for r in ROUTES if not r.identifiants and "get" in r.methodes]

STATUTS_REFUS = {403, 404, 405}

# Paramètres de filtre usuels des listes, chargés des identifiants de B.
FILTRES = {
    "projet": "projets.Projet",
    "projet_id": "projets.Projet",
    "element": "projets.Element",
    "element_id": "projets.Element",
    "equipe": "projets.EquipeChantier",
    "utilisateur": "accounts.Utilisateur",
    "auteur": "accounts.Utilisateur",
    "tiers": "tiers.Tiers",
    "entreprise": "entreprises.Entreprise",
    "entreprise_id": "entreprises.Entreprise",
    "client": "entreprises.Entreprise",
    "rapport": "chantier.RapportJournalier",
}


def valeurs_pour(route, monde) -> dict[str, str]:
    """Les valeurs des paramètres de la route : les identifiants de B, ou `pytest.skip`."""
    valeurs = {}
    for parametre in route.parametres:
        if parametre in VALEURS_FIXES:
            valeurs[parametre] = VALEURS_FIXES[parametre]
            continue
        modele = cible(route, parametre)
        if modele is None and route.plateforme and parametre in PARAMETRES_PLATEFORME:
            valeurs[parametre] = str(uuid.uuid4())  # objet du catalogue : quelconque
            continue
        if modele is None:
            pytest.fail(
                f"{route} : paramètre « {parametre} » (segment « {route.segment(parametre)} ») "
                "sans modèle. Ajoutez-le à CIBLES (outils_etancheite.py)."
            )
        if modele not in monde.exemples_b:
            pytest.skip(f"aucune ligne de B pour {modele}")
        valeurs[parametre] = monde.exemples_b[modele]
    return valeurs


def appeler(client, methode, route, url, jeton):
    entetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}
    if methode == "get":
        return client.get(url, **entetes)
    # Un corps vide, sauf pour les routes qui valident le corps avant les droits (`CORPS`).
    return getattr(client, methode)(
        url,
        data=json.dumps(CORPS.get(route.gabarit, {})),
        content_type="application/json",
        **entetes,
    )


def extrait(reponse) -> str:
    return reponse.content[:300].decode("utf-8", "replace")


@pytest.fixture
def client():
    return Client(HTTP_HOST="localhost")


@pytest.mark.parametrize("route", AVEC_IDENTIFIANT, ids=str)
def test_a_ne_franchit_pas_la_frontiere(route, monde, client):
    url = route.url(valeurs_pour(route, monde))
    for methode in route.methodes:
        avant = temoin(monde.b.pk)
        reponse = appeler(client, methode, route, url, monde.jeton_a)
        apres = temoin(monde.b.pk)

        admis = STATUTS_REFUS | REFUS_ATYPIQUES.get(route.gabarit, (set(), ""))[0]
        assert reponse.status_code in admis, (
            f"{methode.upper()} {url} par A → {reponse.status_code} : {extrait(reponse)}"
        )
        fuites = monde.fuites(reponse.content)
        assert not fuites, f"{methode.upper()} {url} : la réponse à A contient {fuites[:5]}"
        modifiees = sorted(t for t in avant if avant[t] != apres.get(t))
        assert not modifiees, f"{methode.upper()} {url} par A a modifié chez B : {modifiees}"


@pytest.mark.parametrize("route", SANS_IDENTIFIANT, ids=str)
def test_les_listes_de_a_ne_montrent_rien_de_b(route, monde, client):
    url = route.url(VALEURS_FIXES)
    filtres = {
        nom: monde.exemples_b[modele]
        for nom, modele in FILTRES.items()
        if modele in monde.exemples_b
    }
    for parametres in ({}, filtres):
        reponse = client.get(url, parametres, HTTP_AUTHORIZATION=f"Bearer {monde.jeton_a}")
        assert reponse.status_code < 500, f"GET {url} {parametres} → {reponse.status_code}"
        fuites = monde.fuites(reponse.content)
        assert not fuites, f"GET {url} {parametres or ''} : la réponse à A contient {fuites[:5]}"


LECTURES = [
    r
    for r in AVEC_IDENTIFIANT
    if "get" in r.methodes and not r.plateforme and r.gabarit not in CONTROLE_SANS_OBJET
]


@pytest.mark.parametrize("route", LECTURES, ids=str)
def test_controle_positif_b_lit_ses_propres_lignes(route, monde, client):
    url = route.url(valeurs_pour(route, monde))
    reponse = client.get(url, HTTP_AUTHORIZATION=f"Bearer {monde.jeton_b}")
    assert 200 <= reponse.status_code < 300, (
        f"GET {url} par B → {reponse.status_code} : la route ne désigne pas ce que la suite "
        f"croit. {extrait(reponse)}"
    )


def test_toute_route_a_ses_parametres_designes():
    """Un paramètre d'URL inconnu de `CIBLES` fait échouer la suite, au lieu d'être sauté."""
    inconnus = sorted(
        f"{r} ({p})"
        for r in AVEC_IDENTIFIANT
        for p in r.identifiants
        if cible(r, p) is None and not (r.plateforme and p in PARAMETRES_PLATEFORME)
    )
    assert not inconnus, "Paramètres sans modèle dans CIBLES : " + ", ".join(inconnus)
