"""
[D-01, D-06] Filtrage par projet.

VERROUILLÉ. Gemini ne modifie jamais ce fichier.

Portée ENTREPRISE : voit tous les projets, futurs compris.
Portée PROJET     : voit seulement ses projets, à affectation ACTIVE. Sans projet : rien.
"""
import pytest


# ----------------------------------------------------------------------------- liste des projets
@pytest.mark.caracterisation
def test_d01_role_entreprise_voit_tous_les_projets_futurs_compris(fab):
    """[D-01] Un DO voit tous les projets, y compris ceux créés après sa première requête."""
    p1, p2 = fab.creer_projet(), fab.creer_projet()
    client = fab.client_pour(fab.utilisateur_avec_role("DO"))

    vus = fab.ids_de(client.get(fab.url_projets()))
    assert {str(p1.pk), str(p2.pk)} <= vus

    p3 = fab.creer_projet()
    vus = fab.ids_de(client.get(fab.url_projets()))
    assert str(p3.pk) in vus, "un projet créé plus tard doit être visible d'un rôle ENTREPRISE"


@pytest.mark.caracterisation
def test_d01_role_projet_ne_voit_que_ses_projets(fab):
    """[D-01] Un CP affecté à p1 voit p1 et jamais p2."""
    p1, p2 = fab.creer_projet(), fab.creer_projet()
    cp = fab.utilisateur_avec_role("CP")
    fab.affecter(cp, p1)

    vus = fab.ids_de(fab.client_pour(cp).get(fab.url_projets()))
    assert vus == {str(p1.pk)}


@pytest.mark.caracterisation
def test_d01_role_projet_sans_affectation_ne_voit_rien(fab):
    """[D-01] Sans projet : accès à rien (liste vide, et non une erreur)."""
    fab.creer_projet()
    cp = fab.utilisateur_avec_role("CP")

    r = fab.client_pour(cp).get(fab.url_projets())
    assert r.status_code == 200
    assert fab.ids_de(r) == set()


@pytest.mark.caracterisation
def test_d01_affectation_desactivee_ne_donne_plus_acces(fab):
    """[D-01, C-02] Une affectation désactivée ne donne plus aucun projet."""
    p1 = fab.creer_projet()
    cp = fab.utilisateur_avec_role("CP")
    fab.desactiver_affectation(fab.affecter(cp, p1))

    assert fab.ids_de(fab.client_pour(cp).get(fab.url_projets())) == set()


@pytest.mark.nouveau
def test_d01_changer_la_portee_change_la_liste_a_la_requete_suivante(fab):
    """[D-01, B-11] Un CP non affecté voit tous les projets dès que son rôle passe à ENTREPRISE."""
    p1, p2 = fab.creer_projet(), fab.creer_projet()
    cp = fab.utilisateur_avec_role("CP")
    client = fab.client_pour(cp)
    assert fab.ids_de(client.get(fab.url_projets())) == set()

    fab.changer_portee(cp.role, "ENTREPRISE")
    assert {str(p1.pk), str(p2.pk)} <= fab.ids_de(client.get(fab.url_projets()))


# ----------------------------------------------------------------------------- journal des reports (D-06)
@pytest.mark.nouveau
def test_d06_cp_voit_uniquement_les_reports_de_ses_projets(fab):
    """[D-06] CA du cahier : un CP voit uniquement les reports de ses projets."""
    p1, p2 = fab.creer_projet(), fab.creer_projet()
    r1, r2 = fab.creer_report(p1), fab.creer_report(p2)
    cp = fab.utilisateur_avec_role("CP")
    fab.affecter(cp, p1)

    vus = fab.ids_de(fab.client_pour(cp).get(fab.url_journal_reports()))
    assert str(r1.pk) in vus
    assert str(r2.pk) not in vus, "le report d'un projet non affecté fuit"


@pytest.mark.nouveau
def test_d06_role_entreprise_voit_tous_les_reports(fab):
    """[D-06] Un DG voit les reports de tous les projets."""
    p1, p2 = fab.creer_projet(), fab.creer_projet()
    r1, r2 = fab.creer_report(p1), fab.creer_report(p2)

    vus = fab.ids_de(fab.client_pour(fab.obtenir_dg()).get(fab.url_journal_reports()))
    assert {str(r1.pk), str(r2.pk)} <= vus


@pytest.mark.nouveau
def test_d06_role_projet_sans_affectation_ne_voit_aucun_report(fab):
    """[D-06, D-01] Sans affectation : aucun report."""
    fab.creer_report(fab.creer_projet())
    cp = fab.utilisateur_avec_role("CP")

    r = fab.client_pour(cp).get(fab.url_journal_reports())
    assert r.status_code == 200
    assert fab.ids_de(r) == set()


@pytest.mark.nouveau
def test_d06_affectation_desactivee_masque_les_reports(fab):
    """[D-06] Une affectation désactivée ne donne plus les reports du projet."""
    p1 = fab.creer_projet()
    r1 = fab.creer_report(p1)
    cp = fab.utilisateur_avec_role("CP")
    fab.desactiver_affectation(fab.affecter(cp, p1))

    vus = fab.ids_de(fab.client_pour(cp).get(fab.url_journal_reports()))
    assert str(r1.pk) not in vus
