"""
[D-08] Garde unique : une action est autorisée si le code de permission est détenu
ET (portée ENTREPRISE OU affectation ACTIVE au projet).

VERROUILLÉ. Gemini ne modifie jamais ce fichier.

Ces tests ne dépendent d'AUCUN nom de classe : ils vérifient le comportement par des
requêtes HTTP réelles, sur une route de lecture (code projets.lire) et une route
d'écriture (code projets.ecrire).

Le lot 3 CONSERVE le comportement actuel (les changements de droits viennent aux lots 5 et 6).
"""
import os
import re
from pathlib import Path

import pytest

ROOT = Path(os.environ.get("BACKEND_ROOT", Path(__file__).resolve().parents[3]))
EXCLUS = {".git", ".kilo", "__pycache__", "node_modules", "venv", ".venv", "env", "migrations", "staticfiles", "scripts"}

CAS_CARACTERISATION = [
    "dg_non_affecte",
    "do_non_affecte",
    "cp_affecte",
    "cp_non_affecte",
    "cp_affectation_inactive",
    "role_entreprise_sans_code",
    "role_projet_sans_code_affecte",
]
CAS_NOUVEAUX = ["cp_devenu_entreprise"]


def _construire(fab, cas, projet):
    """Retourne (utilisateur, doit_passer)."""
    if cas == "dg_non_affecte":
        return fab.obtenir_dg(), True
    if cas == "do_non_affecte":
        return fab.utilisateur_avec_role("DO"), True
    if cas == "cp_affecte":
        u = fab.utilisateur_avec_role("CP")
        fab.affecter(u, projet)
        return u, True
    if cas == "cp_non_affecte":
        return fab.utilisateur_avec_role("CP"), False
    if cas == "cp_affectation_inactive":
        u = fab.utilisateur_avec_role("CP")
        fab.desactiver_affectation(fab.affecter(u, projet))
        return u, False
    if cas == "role_entreprise_sans_code":
        return fab.creer_utilisateur(fab.creer_role_personnalise(portee="ENTREPRISE")), False
    if cas == "role_projet_sans_code_affecte":
        u = fab.creer_utilisateur(fab.creer_role_personnalise(portee="PROJET"))
        fab.affecter(u, projet)
        return u, False
    if cas == "cp_devenu_entreprise":
        u = fab.utilisateur_avec_role("CP")
        fab.changer_portee(u.role, "ENTREPRISE")
        return u, True
    raise AssertionError(f"cas inconnu : {cas}")


def _a_passe_la_garde(reponse):
    return reponse.status_code not in (401, 403, 404)


# ----------------------------------------------------------------------------- lecture
def _verifier_lecture(fab, projet, cas):
    u, doit_passer = _construire(fab, cas, projet)
    r = fab.client_pour(u).get(fab.url_projet(projet))
    if doit_passer:
        assert r.status_code == 200, f"{cas} : attendu 200, reçu {r.status_code} {r.content[:200]}"
    else:
        assert r.status_code == 403, f"{cas} : attendu 403, reçu {r.status_code}"


def _verifier_ecriture(fab, projet, cas):
    u, doit_passer = _construire(fab, cas, projet)
    r = fab.client_pour(u).post(fab.url_lots(projet), fab.corps_lot(), format="json")
    if doit_passer:
        assert _a_passe_la_garde(r), f"{cas} : la garde a refusé ({r.status_code}) {r.content[:200]}"
    else:
        assert r.status_code == 403, f"{cas} : attendu 403, reçu {r.status_code}"


@pytest.mark.caracterisation
@pytest.mark.parametrize("cas", CAS_CARACTERISATION)
def test_d08_lecture_code_et_portee_ou_affectation(fab, projet, cas):
    """[D-08] Lecture (projets.lire) : code détenu ET (ENTREPRISE OU affectation active)."""
    _verifier_lecture(fab, projet, cas)


@pytest.mark.caracterisation
@pytest.mark.parametrize("cas", CAS_CARACTERISATION)
def test_d08_ecriture_code_et_portee_ou_affectation(fab, projet, cas):
    """[D-08] Écriture (projets.ecrire) : code détenu ET (ENTREPRISE OU affectation active)."""
    _verifier_ecriture(fab, projet, cas)


@pytest.mark.nouveau
@pytest.mark.parametrize("cas", CAS_NOUVEAUX)
def test_d08_la_portee_du_role_est_lue_a_chaque_requete_lecture(fab, projet, cas):
    """[D-08, B-11] Un CP dont le rôle passe à ENTREPRISE accède sans affectation, sans reconnexion."""
    _verifier_lecture(fab, projet, cas)


@pytest.mark.nouveau
@pytest.mark.parametrize("cas", CAS_NOUVEAUX)
def test_d08_la_portee_du_role_est_lue_a_chaque_requete_ecriture(fab, projet, cas):
    """[D-08, B-11] Idem en écriture."""
    _verifier_ecriture(fab, projet, cas)


# ----------------------------------------------------------------------------- comptages statiques
def _fichiers_production():
    for dossier, sous, fichiers in os.walk(ROOT):
        rel = Path(dossier).relative_to(ROOT)
        sous[:] = [s for s in sous if s not in EXCLUS and not s.endswith(".egg-info")]
        if rel.parts[:1] in (("tests",), ("docs",)) or {"tests", "test"} & set(rel.parts):
            sous[:] = []
            continue
        for f in fichiers:
            if f.endswith(".py") and not f.startswith("test_") and not f.endswith("_test.py") and f != "conftest.py":
                yield Path(dossier) / f


def _occurrences(mot, ignorer=()):
    motif = re.compile(rf"\b{re.escape(mot)}\b")
    trouvees = []
    for p in _fichiers_production():
        rel = p.relative_to(ROOT).as_posix()
        if rel in ignorer:
            continue
        for no, ligne in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if motif.search(ligne):
                trouvees.append(f"{rel}:{no}")
    return trouvees


DEFINITION = ("apps/core/permissions.py",)


@pytest.mark.nouveau
def test_d08_plus_aucune_vue_n_utilise_permissionmodule():
    """[D-08] PermissionModule n'apparaît plus hors de sa définition dans apps/core/permissions.py."""
    restes = _occurrences("PermissionModule", ignorer=DEFINITION)
    assert not restes, "PermissionModule encore utilisé :\n" + "\n".join(restes)


@pytest.mark.nouveau
def test_d08_plus_aucune_vue_n_utilise_membreduprojet():
    """[D-08] MembreDuProjet n'apparaît plus hors de apps/core/permissions.py."""
    restes = _occurrences("MembreDuProjet", ignorer=DEFINITION)
    assert not restes, "MembreDuProjet encore utilisé :\n" + "\n".join(restes)


@pytest.mark.nouveau
def test_d08_roleRequis_limite_aux_apps_des_lots_suivants():
    """[D-08] RoleRequis ne subsiste que dans billing, onboarding, tenants (lots 4 et 8), jamais ailleurs."""
    permis = ("apps/billing/", "apps/onboarding/", "apps/tenants/", "apps/core/permissions.py")
    hors = [o for o in _occurrences("RoleRequis") if not o.startswith(permis)]
    assert not hors, "RoleRequis utilisé hors des apps autorisées :\n" + "\n".join(hors)
