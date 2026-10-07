"""
[E-03] Écritures sur le projet et gestion des équipes.
[E-07] Cohérence d'équipe : un membre d'équipe doit obligatoirement être affecté au projet (400 sinon).
Règles :
- Équipes (création, suppression, affectation à activité) sous projets.gerer_equipes.
- Écritures de données (lots, activités, arrêts de chantier selon L5-2) sous projets.ecrire.
- Lectures sous projets.lire (autorisées pour tout membre affecté, refus 403 si non affecté).
- Tout non-affecté reçoit 403 sur les écritures.
"""
import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


@NOUVEAU
def test_e03_post_equipe_autorisations_et_refus(fab):
    """[E-03] POST équipe exige projets.gerer_equipes. CP, CT, DG, AD autorisés ; VI, BAI, CC, DO refusés (403)."""
    dg = fab.acteur("DG")
    ad = fab.acteur("AD")
    projet = fab.creer_projet(createur=dg)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")

    # 1. Autorisés (201)
    # DG et AD non affectés
    client_dg = fab.client_pour(dg)
    r_dg = client_dg.post(fab.url_equipes(projet), fab.corps_equipe("Équipe DG"), format="json")
    assert r_dg.status_code == 201, f"DG doit pouvoir créer une équipe, reçu {r_dg.status_code}"

    client_ad = fab.client_pour(ad)
    r_ad = client_ad.post(fab.url_equipes(projet), fab.corps_equipe("Équipe AD"), format="json")
    assert r_ad.status_code == 201, f"AD doit pouvoir créer une équipe, reçu {r_ad.status_code}"

    # CP et CT affectés
    client_cp = fab.client_pour(cp)
    r_cp = client_cp.post(fab.url_equipes(projet), fab.corps_equipe("Équipe CP"), format="json")
    assert r_cp.status_code == 201, f"CP affecté doit pouvoir créer une équipe, reçu {r_cp.status_code}"

    client_ct = fab.client_pour(ct)
    r_ct = client_ct.post(fab.url_equipes(projet), fab.corps_equipe("Équipe CT"), format="json")
    assert r_ct.status_code == 201, f"CT affecté doit pouvoir créer une équipe, reçu {r_ct.status_code}"

    # 2. Refusés (403) : rôles n'ayant pas projets.gerer_equipes
    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")
    client_vi = fab.client_pour(vi)
    r_vi = client_vi.post(fab.url_equipes(projet), fab.corps_equipe("Équipe VI"), format="json")
    assert r_vi.status_code == 403, f"VI ne doit pas créer d'équipe : reçu {r_vi.status_code}"

    bai = fab.acteur("BAI")
    fab.affecter(projet, bai, role_projet="BAI")
    client_bai = fab.client_pour(bai)
    r_bai = client_bai.post(fab.url_equipes(projet), fab.corps_equipe("Équipe BAI"), format="json")
    assert r_bai.status_code == 403, f"BAI ne doit pas créer d'équipe : reçu {r_bai.status_code}"

    cc = fab.acteur("CC")
    fab.affecter(projet, cc, role_projet="CC")
    client_cc = fab.client_pour(cc)
    r_cc = client_cc.post(fab.url_equipes(projet), fab.corps_equipe("Équipe CC"), format="json")
    assert r_cc.status_code == 403, f"CC ne doit pas créer d'équipe : reçu {r_cc.status_code}"

    do = fab.acteur("DO")
    client_do = fab.client_pour(do)
    r_do = client_do.post(fab.url_equipes(projet), fab.corps_equipe("Équipe DO"), format="json")
    assert r_do.status_code == 403, f"DO ne doit pas créer d'équipe : reçu {r_do.status_code}"


@NOUVEAU
def test_e03_delete_equipe_autorisations_et_refus(fab):
    """[E-03] DELETE équipe exige projets.gerer_equipes. Refus 403 pour VI, CC, DO."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")
    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")

    equipe1 = fab.creer_equipe(projet, "Équipe 1")
    equipe2 = fab.creer_equipe(projet, "Équipe 2")
    equipe3 = fab.creer_equipe(projet, "Équipe 3")

    # 1. Refusés
    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")
    client_vi = fab.client_pour(vi)
    assert client_vi.delete(fab.url_equipe_detail(projet, equipe1)).status_code == 403

    cc = fab.acteur("CC")
    fab.affecter(projet, cc, role_projet="CC")
    client_cc = fab.client_pour(cc)
    assert client_cc.delete(fab.url_equipe_detail(projet, equipe1)).status_code == 403

    do = fab.acteur("DO")
    client_do = fab.client_pour(do)
    assert client_do.delete(fab.url_equipe_detail(projet, equipe1)).status_code == 403

    # 2. Autorisés
    client_ct = fab.client_pour(ct)
    assert client_ct.delete(fab.url_equipe_detail(projet, equipe1)).status_code == 204

    client_cp = fab.client_pour(cp)
    assert client_cp.delete(fab.url_equipe_detail(projet, equipe2)).status_code == 204

    client_dg = fab.client_pour(dg)
    assert client_dg.delete(fab.url_equipe_detail(projet, equipe3)).status_code == 204


@NOUVEAU
def test_e03_affectation_equipe_activite_autorisations_et_refus(fab):
    """[E-03] Affecter une équipe à une activité exige projets.gerer_equipes."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    lot = fab.creer_lot(projet)
    act1 = fab.creer_activite(lot, "Terrassement 1")
    act2 = fab.creer_activite(lot, "Terrassement 2")
    equipe = fab.creer_equipe(projet, "Équipe Terrassement")

    # Refus pour VI affecté et CC affecté
    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")
    client_vi = fab.client_pour(vi)
    r_vi = client_vi.post(
        fab.url_equipe_affectations(projet),
        {"equipe_id": str(equipe.pk), "activite_id": str(act1.pk)},
        format="json",
    )
    assert r_vi.status_code == 403

    # Autorisé pour CP affecté
    client_cp = fab.client_pour(cp)
    r_cp = client_cp.post(
        fab.url_equipe_affectations(projet),
        {"equipe_id": str(equipe.pk), "activite_id": str(act1.pk)},
        format="json",
    )
    assert r_cp.status_code == 201

    # Autorisé pour DG non affecté
    client_dg = fab.client_pour(dg)
    r_dg = client_dg.post(
        fab.url_equipe_affectations(projet),
        {"equipe_id": str(equipe.pk), "activite_id": str(act2.pk)},
        format="json",
    )
    assert r_dg.status_code == 201


@CARAC
def test_e03_ecritures_lots_sous_projets_ecrire(fab):
    """[E-03] POST lot exige projets.ecrire : autorisé pour CP affecté, refus 403 pour VI affecté."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")
    client_cp = fab.client_pour(cp)
    r_cp = client_cp.post(fab.url_lots(projet), fab.corps_lot("Lot CP"), format="json")
    assert r_cp.status_code == 201

    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")
    client_vi = fab.client_pour(vi)
    r_vi = client_vi.post(fab.url_lots(projet), fab.corps_lot("Lot VI"), format="json")
    assert r_vi.status_code == 403


@NOUVEAU
def test_e03_arret_chantier_ecritures_exigent_projets_ecrire(fab):
    """[E-03 / L5-2] POST, PATCH, DELETE arrêt de chantier relèvent de projets.ecrire (refus 403 pour VI, BAI)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")
    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")

    # 1. Refus POST pour VI
    client_vi = fab.client_pour(vi)
    r_post_vi = client_vi.post(
        fab.url_arrets(projet),
        fab.corps_arret(motif="Pluie torrentielle VI"),
        format="json",
    )
    assert r_post_vi.status_code == 403

    # 2. Autorisation POST pour CP affecté
    client_cp = fab.client_pour(cp)
    r_post_cp = client_cp.post(
        fab.url_arrets(projet),
        fab.corps_arret(motif="Pluie torrentielle CP"),
        format="json",
    )
    assert r_post_cp.status_code == 201
    arret_id = r_post_cp.data["id"]

    # 3. Refus PATCH et DELETE pour VI
    url_detail = f"{fab.API}/arrets-chantier/{arret_id}/"
    r_patch_vi = client_vi.patch(url_detail, {"motif": "Modification VI"}, format="json")
    assert r_patch_vi.status_code == 403

    r_del_vi = client_vi.delete(url_detail)
    assert r_del_vi.status_code == 403

    # 4. Autorisation PATCH et DELETE pour CP
    r_patch_cp = client_cp.patch(url_detail, {"motif": "Modification CP"}, format="json")
    assert r_patch_cp.status_code == 200

    r_del_cp = client_cp.delete(url_detail)
    assert r_del_cp.status_code == 204


@CARAC
def test_e03_lectures_equipes_lots_arrets_autorisees_affectes_refus_non_affectes(fab):
    """[E-03] GET équipes, lots, arrêts : autorisé pour tout membre affecté avec projets.lire ; refus 403 si non affecté."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    vi_affecte = fab.acteur("VI")
    fab.affecter(projet, vi_affecte, role_projet="VI")

    vi_non_affecte = fab.acteur("VI")

    client_aff = fab.client_pour(vi_affecte)
    assert client_aff.get(fab.url_equipes(projet)).status_code == 200
    assert client_aff.get(fab.url_lots(projet)).status_code == 200
    assert client_aff.get(fab.url_arrets(projet)).status_code == 200

    client_non_aff = fab.client_pour(vi_non_affecte)
    assert client_non_aff.get(fab.url_equipes(projet)).status_code == 403
    assert client_non_aff.get(fab.url_lots(projet)).status_code == 403
    assert client_non_aff.get(fab.url_arrets(projet)).status_code == 403


@CARAC
def test_e03_non_affecte_toutes_ecritures_refusees(fab):
    """[E-03] Un utilisateur non affecté reçoit 403 sur toute écriture (équipes, lots, arrêts)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    cp_non_aff = fab.acteur("CP")
    client = fab.client_pour(cp_non_aff)

    assert client.post(fab.url_equipes(projet), fab.corps_equipe("Équipe"), format="json").status_code == 403
    assert client.post(fab.url_lots(projet), fab.corps_lot("Lot"), format="json").status_code == 403
    assert client.post(fab.url_arrets(projet), fab.corps_arret(), format="json").status_code == 403


@CARAC
def test_e07_membre_equipe_non_affecte_renvoie_400(fab):
    """[E-07] Tenter d'ajouter à une équipe un utilisateur non affecté au projet renvoie 400."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    non_affecte = fab.acteur("CC")  # créé mais non affecté au projet
    corps = {
        "nom": "Équipe Gros Œuvre",
        "nature": "INTERNE",
        "corps_etat": "Gros Œuvre",
        "chef": {"nom": "Chef externe"},
        "membres": [{"utilisateur_id": str(non_affecte.pk), "fonction": "OUVRIER"}],
    }

    client = fab.client_pour(cp)
    r = client.post(fab.url_equipes(projet), corps, format="json")
    assert r.status_code == 400
