"""
[E-06] Suppression de ProjetRoleModuleOverride et du champ AffectationProjet.role.
role_projet est une étiquette d'affichage sans droits qui synchronise chef_projet et conducteur_travaux.
"""
import os
import re
from pathlib import Path

import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau

ROOT = Path(os.environ.get("BACKEND_ROOT", Path(__file__).resolve().parents[3]))
EXCLUS = {".git", "__pycache__", "node_modules", "venv", ".venv", "env", "migrations", "staticfiles", "tmp_kilo"}


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


@NOUVEAU
def test_e06_route_permissions_roles_supprimee(fab):
    """[E-06] Route /projets/{id}/permissions-roles/ renvoie 404."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    client = fab.client_pour(dg)
    r_get = client.get(fab.url_permissions_roles(projet))
    assert r_get.status_code == 404, f"GET permissions-roles doit être 404, reçu {r_get.status_code}"
    r_put = client.put(fab.url_permissions_roles(projet), {}, format="json")
    assert r_put.status_code == 404, f"PUT permissions-roles doit être 404, reçu {r_put.status_code}"


@NOUVEAU
def test_e06_statique_override_absent():
    """[E-06] Zéro occurrence de ProjetRoleModuleOverride et ProjetPermissionsRolesView en production."""
    termes = ("ProjetRoleModuleOverride", "ProjetPermissionsRolesView")
    coupables = []
    for p in _fichiers_production():
        if p.name == "override.py" and "projets" in p.parts:
            coupables.append(f"Fichier encore présent: {p.relative_to(ROOT).as_posix()}")
        contenu = p.read_text(encoding="utf-8", errors="replace")
        for t in termes:
            if re.search(rf"\b{t}\b", contenu):
                coupables.append(f"{p.relative_to(ROOT).as_posix()}: mention de {t}")

    assert not coupables, "Override de permissions encore présent en production :\n" + "\n".join(coupables)


@NOUVEAU
def test_e06_modele_affectation_sans_champ_role():
    """[E-06] AffectationProjet n'a plus de champ 'role'."""
    from apps.projets.models import AffectationProjet

    champs = [f.name for f in AffectationProjet._meta.get_fields()]
    assert "role" not in champs, "Le champ 'role' doit être supprimé de AffectationProjet"


@NOUVEAU
def test_e06_cc_avec_role_projet_ct_garde_droits_cc(fab):
    """[E-06 CA] Un CC affecté avec role_projet = 'CT' garde ses droits de CC (GET projet 200, POST équipe 403)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cc = fab.acteur("CC")
    fab.affecter(projet, cc, role_projet="CT")

    client_cc = fab.client_pour(cc)
    # Lecture projet : autorisée pour tout membre affecté
    r_get = client_cc.get(fab.url_projet_detail(projet))
    assert r_get.status_code == 200

    # Création d'équipe : CC n'a pas projets.gerer_equipes (CT l'a, mais l'étiquette ne donne aucun droit) -> 403
    r_post_equipe = client_cc.post(
        fab.url_equipes(projet),
        fab.corps_equipe("Équipe CC test"),
        format="json",
    )
    assert r_post_equipe.status_code == 403, (
        f"L'étiquette CT ne doit pas donner gerer_equipes au CC : reçu {r_post_equipe.status_code}"
    )


@NOUVEAU
def test_e06_ct_avec_role_projet_cp_ne_gagne_pas_affecter_membres(fab):
    """[E-06] Un CT affecté avec role_projet = 'CP' ne gagne pas projets.affecter_membres (POST affectation 403)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CP")

    candidat = fab.acteur("VI")
    client_ct = fab.client_pour(ct)
    r_post = client_ct.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r_post.status_code == 403, (
        f"L'étiquette CP ne doit pas accorder affecter_membres au CT : reçu {r_post.status_code}"
    )


@CARAC
def test_e06_synchronisation_chef_projet_et_conducteur(fab):
    """[E-06] role_projet = 'CP' synchronise projet.chef_projet, et 'CT' synchronise conducteur_travaux."""
    from apps.core.enums import RoleProjet
    from apps.projets.models import Projet

    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    ct = fab.acteur("CT")

    # 1. Synchronisation chef de projet
    fab.affecter(projet, cp, role_projet=RoleProjet.CHEF_PROJET)
    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.chef_projet_id == cp.pk

    # 2. Synchronisation conducteur de travaux
    fab.affecter(projet, ct, role_projet=RoleProjet.CONDUCTEUR_TRAVAUX)
    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.conducteur_travaux_id == ct.pk


@CARAC
def test_e06_roles_projet_moa_et_moe_acceptes(fab):
    """[E-06] role_projet = 'MOA' et 'MOE' restent acceptés comme étiquettes d'affichage."""
    from apps.core.enums import RoleProjet

    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    u_moa = fab.acteur("VI")
    u_moe = fab.acteur("VI")

    aff_moa = fab.affecter(projet, u_moa, role_projet=RoleProjet.MAITRE_OUVRAGE)
    aff_moe = fab.affecter(projet, u_moe, role_projet=RoleProjet.MAITRE_OEUVRE)

    assert aff_moa.role_projet == RoleProjet.MAITRE_OUVRAGE
    assert aff_moe.role_projet == RoleProjet.MAITRE_OEUVRE
