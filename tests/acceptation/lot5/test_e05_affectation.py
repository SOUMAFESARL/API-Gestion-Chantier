"""
[E-05] Affectation à un projet : point d'entrée unique et règles d'habilitation.
Acteurs : exige projets.affecter_membres plus (portée ENTREPRISE ou affectation active).
Candidats : seuls les utilisateurs actifs à rôle de portée PROJET sont affectables.
Refus candidat : 400 avec code d'erreur 'candidat_invalide'.
"""
import uuid

import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


@NOUVEAU
def test_e05_acteur_dg_ad_non_affectes_autorises(fab):
    """[E-05] DG et AD (portée ENTREPRISE, non affectés au projet) peuvent affecter un membre."""
    dg = fab.acteur("DG")
    ad = fab.acteur("AD")
    projet = fab.creer_projet(createur=dg)

    # DG non affecté
    candidat_1 = fab.acteur("VI")
    client_dg = fab.client_pour(dg)
    r1 = client_dg.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat_1, role_projet="VI"),
        format="json",
    )
    assert r1.status_code in (200, 201), f"DG non affecté doit pouvoir affecter, reçu {r1.status_code}"

    # AD non affecté
    candidat_2 = fab.acteur("VI")
    client_ad = fab.client_pour(ad)
    r2 = client_ad.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat_2, role_projet="VI"),
        format="json",
    )
    assert r2.status_code in (200, 201), f"AD non affecté doit pouvoir affecter, reçu {r2.status_code}"


@CARAC
def test_e05_acteur_cp_affecte_autorise(fab):
    """[E-05] CP affecté au projet (a projets.affecter_membres) peut affecter un collaborateur."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    candidat = fab.acteur("VI")
    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code in (200, 201)


@CARAC
def test_e05_acteur_cp_non_affecte_refuse(fab):
    """[E-05] CP non affecté au projet reçoit 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp_non_affecte = fab.acteur("CP")

    candidat = fab.acteur("VI")
    client = fab.client_pour(cp_non_affecte)
    r = client.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code == 403


@NOUVEAU
def test_e05_acteur_cp_affectation_desactivee_refuse(fab):
    """[E-05] CP dont l'affectation au projet est inactive reçoit 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    aff = fab.affecter(projet, cp, role_projet="CP")

    with fab._schema():
        aff.est_actif = False
        aff.save(update_fields=["est_actif"])

    candidat = fab.acteur("VI")
    client = fab.client_pour(cp)
    r = client.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code == 403


@NOUVEAU
def test_e05_acteur_do_refuse(fab):
    """[E-05] DO (portée ENTREPRISE mais sans projets.affecter_membres) reçoit 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    do = fab.acteur("DO")

    candidat = fab.acteur("VI")
    client = fab.client_pour(do)
    r = client.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code == 403


@NOUVEAU
def test_e05_acteur_ct_affecte_refuse(fab):
    """[E-05 CA] CT affecté au projet (n'a pas projets.affecter_membres) reçoit 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")

    candidat = fab.acteur("VI")
    client = fab.client_pour(ct)
    r = client.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code == 403


@NOUVEAU
def test_e05_acteur_ct_affecte_avec_etiquette_cp_refuse(fab):
    """[E-05] CT affecté avec role_projet='CP' ne gagne aucun droit et reçoit 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CP")

    candidat = fab.acteur("VI")
    client = fab.client_pour(ct)
    r = client.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code == 403


@NOUVEAU
def test_e05_acteur_cp_affecte_autre_etiquette_autorise(fab):
    """[E-05] CP affecté avec une autre étiquette (ex: role_projet='CT') peut affecter car son rôle système suffit."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CT")

    candidat = fab.acteur("VI")
    client = fab.client_pour(cp)
    r = client.post(
        fab.url_affectations(projet),
        fab.corps_affectation(candidat, role_projet="VI"),
        format="json",
    )
    assert r.status_code in (200, 201)


@NOUVEAU
def test_e05_candidat_portee_entreprise_refuse(fab):
    """[E-05 CA] Affecter un collaborateur à portée ENTREPRISE (ex: DO, DG, AD) renvoie 400 candidat_invalide."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")
    client_cp = fab.client_pour(cp)

    # 1. Candidat DO
    do = fab.acteur("DO")
    r_do = client_cp.post(
        fab.url_affectations(projet),
        fab.corps_affectation(do, role_projet="VI"),
        format="json",
    )
    assert r_do.status_code == 400
    assert r_do.data.get("code") == "candidat_invalide" or "candidat_invalide" in str(r_do.data)

    # 2. Candidat AD
    ad = fab.acteur("AD")
    r_ad = client_cp.post(
        fab.url_affectations(projet),
        fab.corps_affectation(ad, role_projet="VI"),
        format="json",
    )
    assert r_ad.status_code == 400
    assert r_ad.data.get("code") == "candidat_invalide" or "candidat_invalide" in str(r_ad.data)


@NOUVEAU
def test_e05_candidat_inactif_refuse(fab):
    """[E-05] Affecter un collaborateur inactif/suspendu renvoie 400 candidat_invalide."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    suspendu = fab.acteur("VI")
    fab.suspendre_utilisateur(suspendu)

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_affectations(projet),
        fab.corps_affectation(suspendu, role_projet="VI"),
        format="json",
    )
    assert r.status_code == 400
    assert r.data.get("code") == "candidat_invalide" or "candidat_invalide" in str(r.data)


@NOUVEAU
def test_e05_candidat_inconnu_refuse(fab):
    """[E-05] Affecter un identifiant inexistant renvoie 400 candidat_invalide."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    faux_id = uuid.uuid4()
    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_affectations(projet),
        {"utilisateur_id": str(faux_id), "role_projet": "VI"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data.get("code") == "candidat_invalide" or "candidat_invalide" in str(r.data)


@CARAC
def test_e05_candidat_cc_actif_accepte(fab):
    """[E-05] Affecter un collaborateur actif à rôle PROJET (ex: CC) est accepté."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    cc = fab.acteur("CC")
    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_affectations(projet),
        fab.corps_affectation(cc, role_projet="CC"),
        format="json",
    )
    assert r.status_code in (200, 201)


@NOUVEAU
def test_e05_patch_delete_acteurs_autorises_et_refus(fab):
    """[E-05] PATCH et DELETE d'une affectation : refus 403 pour CT et DO ; l'affectation reste active après refus."""
    from apps.projets.models import AffectationProjet

    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")
    do = fab.acteur("DO")

    cible = fab.acteur("CC")
    aff = fab.affecter(projet, cible, role_projet="CC")

    # 1. Refus PATCH par CT affecté
    client_ct = fab.client_pour(ct)
    r_patch_ct = client_ct.patch(
        fab.url_affectation_detail(projet, aff),
        {"role_projet": "VI"},
        format="json",
    )
    assert r_patch_ct.status_code == 403

    # 2. Refus DELETE par DO
    client_do = fab.client_pour(do)
    r_del_do = client_do.delete(fab.url_affectation_detail(projet, aff))
    assert r_del_do.status_code == 403

    # Vérification : l'affectation reste active en base après les refus
    with fab._schema():
        aff_db = AffectationProjet.objects.get(pk=aff.pk)
        assert aff_db.est_actif is True

    # 3. CP affecté peut modifier (PATCH)
    client_cp = fab.client_pour(cp)
    r_patch_cp = client_cp.patch(
        fab.url_affectation_detail(projet, aff),
        {"role_projet": "VI"},
        format="json",
    )
    assert r_patch_cp.status_code == 200

    # 4. DG non affecté peut révoquer (DELETE)
    client_dg = fab.client_pour(dg)
    r_del_dg = client_dg.delete(fab.url_affectation_detail(projet, aff))
    assert r_del_dg.status_code in (200, 204)
