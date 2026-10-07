"""
[F-01, F-02] Lectures de rôles sous administration.roles_gerer, et unification des deux familles :
    /api/v1/roles/...            (alias, G-02)
    /api/v1/parametres/roles/... (route de référence)

VERROUILLÉ. Gemini ne modifie jamais ce fichier.
"""
import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau

FAMILLES = ["/roles/", "/parametres/roles/"]

LECTURE_AUTORISEE = [
    pytest.param("/roles/", "DG", marks=CARAC, id="roles-DG"),
    pytest.param("/parametres/roles/", "DG", marks=CARAC, id="parametres-DG"),
    pytest.param("/parametres/roles/", "AD", marks=CARAC, id="parametres-AD"),
    pytest.param("/roles/", "AD", marks=NOUVEAU, id="roles-AD"),
]

ACTEURS_SANS_DROIT = ["DO", "CP", "DF", "CT", "perso_entreprise"]


@pytest.mark.parametrize("famille,nom_acteur", LECTURE_AUTORISEE)
def test_f01_lecture_liste_et_detail_sous_roles_gerer(fab, famille, nom_acteur):
    """[F-01] Liste et détail d'un rôle : autorisés au DG et à l'AD (administration.roles_gerer)."""
    client = fab.client_pour(fab.acteur(nom_acteur))

    r = client.get(fab.url_liste_roles(famille))
    assert r.status_code == 200, f"liste {famille} pour {nom_acteur} : {r.status_code}"

    r = client.get(fab.url_role(famille, fab.role_systeme("CT")))
    assert r.status_code == 200, f"détail {famille} pour {nom_acteur} : {r.status_code}"


@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
@pytest.mark.parametrize("nom_acteur", ACTEURS_SANS_DROIT)
def test_f01_lecture_refusee_sans_roles_gerer(fab, famille, nom_acteur):
    """[F-01] Sans administration.roles_gerer, liste et détail sont refusés (403)."""
    client = fab.client_pour(fab.acteur(nom_acteur))

    assert client.get(fab.url_liste_roles(famille)).status_code == 403
    assert client.get(fab.url_role(famille, fab.role_systeme("CT"))).status_code == 403


@NOUVEAU
@pytest.mark.parametrize("nom_acteur", ["DG", "AD", "DO", "CP", "DF", "perso_entreprise"])
def test_f02_les_deux_familles_donnent_la_meme_reponse(fab, nom_acteur):
    """[F-02] Pour un même acteur, /roles/ et /parametres/roles/ répondent par le même statut (liste et détail)."""
    client = fab.client_pour(fab.acteur(nom_acteur))
    role = fab.role_systeme("CT")

    listes = {f: client.get(fab.url_liste_roles(f)).status_code for f in FAMILLES}
    details = {f: client.get(fab.url_role(f, role)).status_code for f in FAMILLES}

    assert len(set(listes.values())) == 1, f"listes divergentes pour {nom_acteur} : {listes}"
    assert len(set(details.values())) == 1, f"détails divergents pour {nom_acteur} : {details}"


# ---------------------------------------------------------------------------- écritures : même refus des deux côtés
@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
def test_f02_creation_refusee_sans_roles_gerer(fab, famille):
    """[F-02] Un CP ne crée aucun rôle, par aucune des deux familles."""
    client = fab.client_pour(fab.acteur("CP"))
    r = client.post(fab.url_liste_roles(famille), {}, format="json")
    assert r.status_code == 403


@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
def test_f02_modification_refusee_sans_roles_gerer(fab, famille):
    """[F-02] Un CP ne modifie aucun rôle, par aucune des deux familles."""
    client = fab.client_pour(fab.acteur("CP"))
    r = client.patch(fab.url_role(famille, fab.role_systeme("CT")), fab.corps_inoffensif(), format="json")
    assert r.status_code == 403


@CARAC
@pytest.mark.parametrize("famille", FAMILLES)
def test_f02_suppression_refusee_sans_roles_gerer(fab, famille):
    """[F-02] Un CP ne supprime ni ne réassigne aucun rôle, par aucune des deux familles."""
    client = fab.client_pour(fab.acteur("CP"))
    r = client.post(fab.url_supprimer_role(famille, fab.creer_role_personnalise()), {}, format="json")
    assert r.status_code == 403


@pytest.mark.parametrize(
    "famille",
    [
        pytest.param("/roles/", marks=NOUVEAU),
        pytest.param("/parametres/roles/", marks=CARAC),
    ],
)
def test_f02_l_ad_peut_modifier_un_role_personnalise_par_les_deux_familles(fab, famille):
    """[F-02, B-07] L'AD passe la garde sur un rôle PERSONNALISÉ, quelle que soit la famille."""
    role = fab.creer_role_personnalise()
    client = fab.client_pour(fab.acteur("AD"))
    r = client.patch(fab.url_role(famille, role), fab.corps_inoffensif(), format="json")
    assert fab.a_passe_la_garde(r), f"{famille} : {r.status_code} {r.content[:200]}"
