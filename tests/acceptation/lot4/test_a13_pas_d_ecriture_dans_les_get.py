"""
[A-13] Aucun écrasement, aucune écriture dans un GET.

VERROUILLÉ. Gemini ne modifie jamais ce fichier.

Limite connue, assumée : le scénario « table des rôles vide » ne peut pas être monté par HTTP
(la clé du rôle sur le collaborateur est en PROTECT). Il est donc couvert par deux tests statiques
(plus aucun appel paresseux dans les deux vues de liste) et par des tests de non-régression en base.
"""
import os
import re
from pathlib import Path

import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau

ROOT = Path(os.environ.get("BACKEND_ROOT", Path(__file__).resolve().parents[3]))
EXCLUS = {".git", "__pycache__", "node_modules", "venv", ".venv", "env", "migrations", "staticfiles"}
FAMILLES = ["/roles/", "/parametres/roles/"]
VUES_DE_LISTE = ("RoleListCreateView", "ParametresRoleListCreateView")
APPELS_PARESSEUX = ("initialiser_roles_par_defaut", "appliquer_modeles_roles")


def _fichiers_production():
    for dossier, sous, fichiers in os.walk(ROOT):
        rel = Path(dossier).relative_to(ROOT)
        sous[:] = [s for s in sous if s not in EXCLUS and not s.endswith(".egg-info")]
        if rel.parts[:1] in (("tests",), ("docs",)) or {"tests", "test"} & set(rel.parts):
            sous[:] = []
            continue
        for f in fichiers:
            if f.endswith(".py") and not f.startswith("test_") and f != "conftest.py":
                yield Path(dossier) / f


def _fichiers_definissant(classe):
    motif = re.compile(rf"^\s*class\s+{re.escape(classe)}\b", re.M)
    return [
        p for p in _fichiers_production()
        if motif.search(p.read_text(encoding="utf-8", errors="replace"))
    ]


# ----------------------------------------------------------------------------- statique
@NOUVEAU
@pytest.mark.parametrize("vue", VUES_DE_LISTE)
@pytest.mark.parametrize("appel", APPELS_PARESSEUX)
def test_a13_les_vues_de_liste_n_appellent_plus_de_creation_de_roles(vue, appel):
    """[A-13] Le fichier qui définit chaque vue de liste de rôles ne mentionne plus la création paresseuse."""
    fichiers = _fichiers_definissant(vue)
    assert fichiers, f"vue {vue} introuvable : le fichier a-t-il été renommé ?"
    coupables = []
    for p in fichiers:
        for no, ligne in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if re.search(rf"\b{appel}\b", ligne):
                coupables.append(f"{p.relative_to(ROOT).as_posix()}:{no}")
    assert not coupables, f"{appel} encore référencé :\n" + "\n".join(coupables)


@NOUVEAU
def test_a13_aucun_get_de_vue_n_appelle_la_creation_paresseuse():
    """[A-13] Aucun fichier de vues (dossier views ou views.py) ne référence la création paresseuse."""
    coupables = []
    for p in _fichiers_production():
        rel = p.relative_to(ROOT).as_posix()
        if "/views/" not in rel and not rel.endswith("views.py"):
            continue
        for no, ligne in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if any(re.search(rf"\b{a}\b", ligne) for a in APPELS_PARESSEUX):
                coupables.append(f"{rel}:{no}")
    assert not coupables, "Appels paresseux dans des vues :\n" + "\n".join(coupables)


# ----------------------------------------------------------------------------- non-régression en base
@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
def test_a13_un_get_d_une_liste_ou_d_un_detail_n_ecrit_rien(fab, famille):
    """[A-13] Un GET de liste et de détail n'émet aucun INSERT, UPDATE ni DELETE."""
    client = fab.client_pour(fab.obtenir_dg())
    role = fab.role_systeme("CT")
    ecritures = fab.ecritures_sql_pendant(
        lambda: (
            client.get(fab.url_liste_roles(famille)),
            client.get(fab.url_role(famille, role)),
        )
    )
    assert ecritures == [], "Écritures SQL pendant des GET :\n" + "\n".join(ecritures)


@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
def test_a13_un_role_systeme_supprime_n_est_pas_recree_par_un_get(fab, famille):
    """[A-13] Un GET ne recrée pas un rôle système manquant."""
    fab.supprimer_role_sans_utilisateur("MAG")
    avant = fab.nombre_de_roles()

    r = fab.client_pour(fab.obtenir_dg()).get(fab.url_liste_roles(famille))

    assert r.status_code == 200
    assert fab.nombre_de_roles() == avant, "un GET a modifié le nombre de rôles"
    codes = {ligne.get("code") for ligne in fab.liste_de(r)}
    assert "MAG" not in codes


@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
def test_a13_un_role_systeme_modifie_en_base_n_est_pas_ecrase_par_un_get(fab, famille):
    """[A-13] Un rôle système modifié n'est pas remis à l'état du modèle par un GET."""
    role = fab.role_systeme("CT")
    fab.changer_portee(role, "ENTREPRISE")

    fab.client_pour(fab.obtenir_dg()).get(fab.url_liste_roles(famille))

    assert fab.role_systeme("CT").portee == "ENTREPRISE"
