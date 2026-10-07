"""
[B-04, B-06, B-07, B-08, B-09, B-10, B-12] Administration des rôles et gouvernance de l'AD.

Règles couvertes :
- B-04 : Droits d'administration fixes de l'AD dans le code.
- B-06 : L'AD ne peut ni modifier, ni suspendre, ni supprimer un autre AD ni lui-même (seul le DG gère les AD).
- B-07 : L'AD ne modifie aucun rôle système (403).
- B-08 : L'AD ne donne que ce qu'il possède (403 si permission hors périmètre).
- B-09 : L'AD n'attribue qu'un rôle dont toutes les permissions font partie des siennes (refus 403 pour AD, DG, DF).
- B-10 : Pouvoirs du DG sur les rôles (peut tout modifier sauf son propre rôle).
- B-12 : Cycle de vie des rôles personnalisés.
"""
import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau

FAMILLES = ["/roles/", "/parametres/roles/"]


# ----------------------------------------------------------------------------- B-04
@NOUVEAU
def test_b04_droits_administration_fixes_ad(fab):
    """[B-04] L'AD possède en dur dans le code ses 6 droits d'administration fixes, et ni entreprise_modifier ni abonnement_gerer."""
    ad = fab.acteur("AD")
    perms_ad = fab.permissions_de(ad)

    for code_admin in fab.ADMIN_AD:
        assert code_admin in perms_ad, f"Droit d'administration manquant pour l'AD : {code_admin}"

    for code_dg in fab.ADMIN_DG_SEUL:
        assert code_dg not in perms_ad, f"Droit réservé au DG indûment accordé à l'AD : {code_dg}"


# ----------------------------------------------------------------------------- B-06
@NOUVEAU
def test_b06_ad_ne_peut_pas_modifier_ni_suspendre_ni_supprimer_ad(fab):
    """[B-06] Un AD ne peut ni modifier le rôle, ni suspendre, ni supprimer un autre AD ni lui-même (403)."""
    ad1 = fab.acteur("AD")
    ad2 = fab.acteur("AD")
    client_ad1 = fab.client_pour(ad1)

    # 1. Tenter de modifier le rôle d'un autre AD
    r = client_ad1.patch(
        fab.url_collaborateur(ad2),
        {"role_global": "CP"},
        format="json",
    )
    assert r.status_code == 403, f"Modification du rôle d'un autre AD attendue 403, reçu {r.status_code}"

    # 2. Tenter de modifier son propre rôle
    r = client_ad1.patch(
        fab.url_collaborateur(ad1),
        {"role_global": "CP"},
        format="json",
    )
    assert r.status_code == 403, f"Modification de son propre rôle attendue 403, reçu {r.status_code}"

    # 3. Tenter de suspendre un autre AD
    r = client_ad1.post(fab.url_suspendre(ad2), {}, format="json")
    assert r.status_code == 403, f"Suspension d'un autre AD attendue 403, reçu {r.status_code}"

    # 4. Tenter de suspendre son propre compte
    r = client_ad1.post(fab.url_suspendre(ad1), {}, format="json")
    assert r.status_code == 403, f"Suspension de son propre compte attendue 403, reçu {r.status_code}"

    # 5. Tenter de supprimer un autre AD
    r = client_ad1.delete(fab.url_collaborateur(ad2))
    assert r.status_code == 403, f"Suppression d'un autre AD attendue 403, reçu {r.status_code}"


@NOUVEAU
def test_b06_dg_peut_gerer_ad(fab):
    """[B-06] Seul le DG a autorité pour suspendre ou modifier un AD."""
    dg = fab.obtenir_dg()
    ad = fab.acteur("AD")
    client_dg = fab.client_pour(dg)

    # Suspendre l'AD par le DG
    r = client_dg.post(fab.url_suspendre(ad), {}, format="json")
    assert r.status_code in (200, 204), f"Le DG doit pouvoir suspendre un AD : {r.status_code}"


# ----------------------------------------------------------------------------- B-07
@NOUVEAU
@pytest.mark.parametrize("famille", FAMILLES)
@pytest.mark.parametrize("code_role_systeme", ["CT", "CP", "DO", "DF", "CC", "MAG"])
def test_b07_ad_ne_peut_pas_modifier_role_systeme(fab, famille, code_role_systeme):
    """[B-07] Un AD ne modifie pas les permissions d'un rôle système (403)."""
    ad = fab.acteur("AD")
    client_ad = fab.client_pour(ad)
    role = fab.role_systeme(code_role_systeme)

    r = client_ad.patch(
        fab.url_role(famille, role),
        {"permissions": ["projets.lire"]},
        format="json",
    )
    assert r.status_code == 403, f"AD modifiant {code_role_systeme} sur {famille} : attendu 403, reçu {r.status_code}"


# ----------------------------------------------------------------------------- B-08
@NOUVEAU
@pytest.mark.parametrize("famille", FAMILLES)
def test_b08_ad_ne_peut_pas_donner_permission_qu_il_n_a_pas(fab, famille):
    """[B-08] Pour créer ou modifier un rôle, l'AD ne peut accorder que des permissions qu'il possède lui-même."""
    ad = fab.acteur("AD")
    client_ad = fab.client_pour(ad)

    # projets.voir_montants n'est pas possédé par l'AD
    r = fab.creer_role_par_api(
        client_ad,
        nom="PERSO_ILLICITE",
        portee="PROJET",
        codes=["projets.lire", "projets.voir_montants"],
        famille=famille,
    )
    assert r.status_code == 403, f"Création avec permission hors périmètre attendue 403, reçu {r.status_code}"


@NOUVEAU
@pytest.mark.parametrize("famille", FAMILLES)
def test_b08_ad_peut_donner_permissions_qu_il_possede(fab, famille):
    """[B-08] L'AD peut créer un rôle personnalisé avec des permissions qu'il possède."""
    ad = fab.acteur("AD")
    client_ad = fab.client_pour(ad)

    r = fab.creer_role_par_api(
        client_ad,
        nom="PERSO_AUTORISE",
        portee="PROJET",
        codes=["projets.lire"],
        famille=famille,
    )
    assert r.status_code == 201, f"Création autorisée attendue 201, reçu {r.status_code} {r.content[:200]}"


# ----------------------------------------------------------------------------- B-09 & Point 6
@NOUVEAU
@pytest.mark.parametrize("role_interdit", ["DF", "AD", "DG"])
def test_b09_ad_ne_peut_pas_attribuer_df_ad_dg(fab, role_interdit):
    """[B-09] L'AD ne peut pas attribuer un rôle dont toutes les permissions ne font pas partie des siennes (refus 403 pour DF, AD, DG)."""
    ad = fab.acteur("AD")
    cible = fab.utilisateur_avec_role("CC")
    client_ad = fab.client_pour(ad)

    r = client_ad.patch(
        fab.url_collaborateur(cible),
        {"role_global": role_interdit},
        format="json",
    )
    assert r.status_code == 403, f"Attribution de {role_interdit} par AD attendue 403, reçu {r.status_code}"


@NOUVEAU
def test_b09_ad_peut_attribuer_role_inclus(fab):
    """[B-09] L'AD peut attribuer un rôle dont les permissions font partie des siennes (ex: BAI ou rôle personnalisé inclus)."""
    ad = fab.acteur("AD")
    cible = fab.utilisateur_avec_role("CC")
    client_ad = fab.client_pour(ad)

    r = client_ad.patch(
        fab.url_collaborateur(cible),
        {"role_global": "BAI"},
        format="json",
    )
    assert r.status_code == 200, f"Attribution autorisée attendue 200, reçu {r.status_code} {r.content[:200]}"
    assert fab.role_code_de(cible) == "BAI"


# ----------------------------------------------------------------------------- B-10
@NOUVEAU
@pytest.mark.parametrize("famille", FAMILLES)
def test_b10_dg_modifie_permissions_roles(fab, famille):
    """[B-10] Le DG modifie les permissions de n'importe quel rôle (système compris) sauf le sien."""
    dg = fab.obtenir_dg()
    client_dg = fab.client_pour(dg)
    role_ct = fab.role_systeme("CT")

    r = client_dg.patch(
        fab.url_role(famille, role_ct),
        {"permissions": ["projets.lire", "chantier.rediger"], "confirmer": True},
        format="json",
    )
    assert r.status_code == 200, f"Le DG doit pouvoir modifier CT sur {famille} : {r.status_code}"


# ----------------------------------------------------------------------------- B-12
@NOUVEAU
@pytest.mark.parametrize("famille", FAMILLES)
def test_b12_creation_et_suppression_role_personnalise(fab, famille):
    """[B-12] Un rôle personnalisé peut être créé puis supprimé avec réassignation des collaborateurs."""
    dg = fab.obtenir_dg()
    client_dg = fab.client_pour(dg)

    # 1. Création
    r = fab.creer_role_par_api(
        client_dg,
        nom="PERSO_CYCLE_VIE",
        portee="PROJET",
        codes=["projets.lire"],
        famille=famille,
    )
    assert r.status_code == 201, f"Création attendue 201 : {r.status_code}"
    role_id = r.json()["id"]

    # 2. Suppression avec réassignation vers VI
    role_vi = fab.role_systeme("VI")
    r_del = client_dg.post(
        f"{fab.url_liste_roles(famille)}{role_id}/supprimer/",
        {"role_reassignation_id": str(role_vi.id)},
        format="json",
    )
    assert r_del.status_code in (200, 204), f"Suppression attendue 200/204 : {r_del.status_code}"
