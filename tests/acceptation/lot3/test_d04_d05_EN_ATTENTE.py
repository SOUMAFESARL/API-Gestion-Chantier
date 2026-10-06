"""
[D-04, D-05] EN ATTENTE : NE PAS VERROUILLER, NE PAS DONNER À GEMINI TANT QUE CE BANDEAU EST LÀ.

Ce fichier ne devient verrouillable qu'après :
  1. décision de Durel sur L3-3 (MotifReport, route inchangée), L3-5, L3-6, L3-7 (voir 04-cadrage-tests-lot3.md) ;
  2. l'inventaire I-07 FINAL (tableau module -> portée, sans A_CONFIRMER), pour savoir quels modules sont globaux ;
  3. la complétion par Claude de fab.definir_permissions et fab.corps_permissions, d'après les fabriques du lot 1.

Les tests ci-dessous sont écrits d'après les propositions L3-2 et L3-3 et sont à relire.
"""
import pytest


@pytest.mark.nouveau
def test_d04_motifs_report_module_global_role_projet_avec_permission(fab):
    """[D-04] MotifReport est sans projet : un rôle PROJET qui a pilotage.lire le lit en entier, sans affectation."""
    role = fab.creer_role_personnalise(portee="PROJET")
    fab.definir_permissions(role, ["pilotage.lire"])
    u = fab.creer_utilisateur(role)

    r = fab.client_pour(u).get(fab.url_motifs_report())
    assert r.status_code == 200


@pytest.mark.nouveau
def test_d04_motifs_report_refuse_sans_pilotage_lire(fab):
    """[D-04] Un rôle PROJET qui a projets.lire mais pas pilotage.lire ne lit plus les motifs."""
    role = fab.creer_role_personnalise(portee="PROJET")
    fab.definir_permissions(role, ["projets.lire"])
    u = fab.creer_utilisateur(role)

    r = fab.client_pour(u).get(fab.url_motifs_report())
    assert r.status_code == 403


@pytest.mark.nouveau
def test_d04_la_route_des_motifs_n_a_pas_change(fab):
    """[G-02] Aucune route renommée : /projets/motifs-report/ répond toujours pour un DG."""
    r = fab.client_pour(fab.obtenir_dg()).get(fab.url_motifs_report())
    assert r.status_code == 200


@pytest.mark.nouveau
def test_d05_avertissement_permission_globale_sur_role_projet(fab):
    """[D-05] Cocher une permission d'un module GLOBAL (pilotage) sur un rôle PROJET renvoie un avertissement."""
    dg = fab.obtenir_dg()
    role = fab.creer_role_personnalise(portee="PROJET")

    r = fab.client_pour(dg).patch(
        f"{fab.API}/parametres/roles/{role.pk}/",
        fab.corps_permissions(["pilotage.lire"]),
        format="json",
    )
    assert r.status_code == 200, r.content
    assert "permission_globale_sur_role_projet" in r.json().get("avertissements", [])


@pytest.mark.nouveau
def test_d05_pas_d_avertissement_pour_un_role_entreprise(fab):
    """[D-05] Aucun avertissement quand le rôle est à portée ENTREPRISE."""
    dg = fab.obtenir_dg()
    role = fab.creer_role_personnalise(portee="ENTREPRISE")

    r = fab.client_pour(dg).patch(
        f"{fab.API}/parametres/roles/{role.pk}/",
        fab.corps_permissions(["pilotage.lire"]),
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.json().get("avertissements", []) == []


@pytest.mark.nouveau
def test_d05_pas_d_avertissement_pour_un_module_par_projet(fab):
    """[D-05] Aucun avertissement pour une permission d'un module PAR PROJET (projets.lire) sur un rôle PROJET."""
    dg = fab.obtenir_dg()
    role = fab.creer_role_personnalise(portee="PROJET")

    r = fab.client_pour(dg).patch(
        f"{fab.API}/parametres/roles/{role.pk}/",
        fab.corps_permissions(["projets.lire"]),
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.json().get("avertissements", []) == []
