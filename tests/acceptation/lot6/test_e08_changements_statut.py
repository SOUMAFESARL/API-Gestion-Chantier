"""
[E-08] Tests d'acceptation du Lot 6 : Séparation des permissions de statut et suppression de l'exception historique.
Règles : E-08 (cahier-regles.md).
"""
import pytest
from apps.core.enums import StatutProjet
from apps.projets.models import Projet

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


@NOUVEAU
def test_e08_vi_ayant_projets_lire_seul_refuse_403(fab):
    """[E-08] Suppression de l'exception historique : un VI affecté (projets.lire seul) reçoit 403 sur PATCH statut."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")

    client_vi = fab.client_pour(vi)
    r = client_vi.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.SUSPENDU),
        format="json",
    )
    assert r.status_code == 403, f"VI avec projets.lire seul doit recevoir 403, reçu {r.status_code}"

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.EN_COURS, "Le statut en base ne doit pas avoir changé après refus"


@NOUVEAU
def test_e08_cp_autorise_sur_statuts_operationnels(fab):
    """[E-08] Un CP affecté (détenteur de projets.changer_statut) peut suspendre un chantier (200)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.SUSPENDU),
        format="json",
    )
    assert r.status_code == 200, f"CP affecté doit pouvoir suspendre le projet, reçu {r.status_code}"

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.SUSPENDU


@NOUVEAU
def test_e08_cp_refuse_403_sur_resilier_archiver(fab):
    """[E-08] Un CP n'a pas projets.resilier_archiver : tenter de résilier renvoie 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.RESILIE),
        format="json",
    )
    assert r.status_code == 403, f"CP ne possède pas projets.resilier_archiver, reçu {r.status_code}"

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.EN_COURS


@NOUVEAU
def test_e08_do_autorise_sur_resiliation(fab):
    """[E-08] Un DO (détenteur de projets.resilier_archiver, portée ENTREPRISE) peut résilier un projet (200)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    do = fab.acteur("DO")
    client_do = fab.client_pour(do)
    r = client_do.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.RESILIE),
        format="json",
    )
    assert r.status_code == 200, f"DO doit pouvoir résilier un chantier, reçu {r.status_code}"

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.RESILIE


@NOUVEAU
def test_e08_reouverture_projet_clos_exige_resilier_archiver(fab):
    """[E-08] Sortir d'un statut clos (RESILIE -> EN_COURS) exige projets.resilier_archiver. DO autorisé, CP refusé."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    # 1. CP tente de réactiver : 403
    client_cp = fab.client_pour(cp)
    r_cp = client_cp.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.EN_COURS),
        format="json",
    )
    assert r_cp.status_code == 403, f"CP ne doit pas pouvoir réactiver un projet résilié, reçu {r_cp.status_code}"

    # 2. DO (a projets.resilier_archiver) réactive : 200
    do = fab.acteur("DO")
    client_do = fab.client_pour(do)
    r_do = client_do.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.EN_COURS),
        format="json",
    )
    assert r_do.status_code == 200, f"DO doit pouvoir réactiver un projet résilié, reçu {r_do.status_code}"

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.EN_COURS


@NOUVEAU
def test_e08_ct_ayant_projets_ecrire_seul_refuse_sur_statut(fab):
    """[E-08] Séparation stricte : un CT (qui a projets.ecrire mais pas changer_statut) reçoit 403 sur PATCH statut."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")

    client_ct = fab.client_pour(ct)
    r = client_ct.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.SUSPENDU),
        format="json",
    )
    assert r.status_code == 403, f"CT n'a pas projets.changer_statut, reçu {r.status_code}"


@CARAC
def test_e08_appel_anonyme_refuse_401(fab):
    """[E-08] Une requête sans jeton JWT sur PATCH statut renvoie 401."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    from rest_framework.test import APIClient
    client_anonyme = APIClient()
    r = client_anonyme.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.SUSPENDU),
        format="json",
        HTTP_HOST=fab.HOST,
    )
    assert r.status_code == 401


@CARAC
def test_e08_acteur_non_affecte_refuse_403(fab):
    """[E-08] Un acteur à portée PROJET non affecté (CP non affecté) reçoit 403 (Garde unique D-08)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")  # Non affecté

    client_cp = fab.client_pour(cp)
    r = client_cp.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.SUSPENDU),
        format="json",
    )
    assert r.status_code == 403


@NOUVEAU
def test_e08_dg_pouvoirs_souverains_sur_tous_statuts(fab):
    """[E-08] Le DG a toutes les permissions calculées : il peut suspendre, résilier et archiver."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    client_dg = fab.client_pour(dg)

    # 1. Suspendre
    r1 = client_dg.patch(fab.url_projet_detail(projet), fab.corps_statut(StatutProjet.SUSPENDU), format="json")
    assert r1.status_code == 200

    # 2. Résilier
    r2 = client_dg.patch(fab.url_projet_detail(projet), fab.corps_statut(StatutProjet.RESILIE), format="json")
    assert r2.status_code == 200

    # 3. Archiver
    r3 = client_dg.patch(fab.url_projet_detail(projet), fab.corps_statut(StatutProjet.ARCHIVE), format="json")
    assert r3.status_code == 200
