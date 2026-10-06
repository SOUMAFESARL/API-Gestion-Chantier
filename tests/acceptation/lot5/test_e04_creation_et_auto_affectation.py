"""
[E-04] Création de projet et auto-affectation conditionnelle du créateur.
Règles :
- Créateur à portée ENTREPRISE (DG, AD, DO) : aucune affectation créée.
- Créateur à portée PROJET (ex: CP auquel on a accordé projets.creer) : auto-affectation active,
  role_projet vide, projet.chef_projet non modifié.
- Un utilisateur à portée PROJET sans projets.creer reçoit 403.
- Si le même utilisateur crée deux projets, deux affectations distinctes sont créées (une par projet).
"""
import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


@NOUVEAU
def test_e04_creation_par_portee_entreprise_aucune_affectation(fab):
    """[E-04] DG ou AD créent un projet : 201, mais AUCUNE AffectationProjet n'est créée."""
    from apps.projets.models import AffectationProjet

    dg = fab.acteur("DG")
    ad = fab.acteur("AD")

    # 1. DG crée un projet
    client_dg = fab.client_pour(dg)
    r_dg = client_dg.post(fab.url_projets(), fab.corps_projet("Projet Tour A DG"), format="json")
    assert r_dg.status_code == 201, f"DG doit pouvoir créer un projet, reçu {r_dg.status_code}"
    id_projet_dg = r_dg.data["id"]

    with fab._schema():
        affs_dg = list(AffectationProjet.objects.filter(projet_id=id_projet_dg))
        assert len(affs_dg) == 0, f"Aucune affectation ne doit être créée pour le DG, trouvé: {affs_dg}"

    # 2. AD crée un projet
    client_ad = fab.client_pour(ad)
    r_ad = client_ad.post(fab.url_projets(), fab.corps_projet("Projet Tour B AD"), format="json")
    assert r_ad.status_code == 201, f"AD doit pouvoir créer un projet, reçu {r_ad.status_code}"
    id_projet_ad = r_ad.data["id"]

    with fab._schema():
        affs_ad = list(AffectationProjet.objects.filter(projet_id=id_projet_ad))
        assert len(affs_ad) == 0, f"Aucune affectation ne doit être créée pour l'AD, trouvé: {affs_ad}"


@CARAC
def test_e04_cp_sans_droit_creer_refuse(fab):
    """[E-04] Un Chef de Projet n'ayant pas projets.creer reçoit 403 à la création d'un projet."""
    cp = fab.acteur("CP")
    client_cp = fab.client_pour(cp)
    r = client_cp.post(fab.url_projets(), fab.corps_projet("Projet Refusé"), format="json")
    assert r.status_code == 403, f"CP sans projets.creer doit recevoir 403, reçu {r.status_code}"


@NOUVEAU
def test_e04_ca_cp_avec_droit_creer_auto_affectation(fab):
    """[E-04 CA] Le DG coche projets.creer au CP ; le CP crée un projet (201) et est auto-affecté."""
    from apps.projets.models import AffectationProjet, Projet

    cp = fab.acteur("CP")
    role_cp = cp.role

    # Le DG donne la permission projets.creer au rôle CP
    # On ajoute projets.creer aux permissions actuelles du CP
    perms_actuelles = set(fab.permissions_de(cp))
    perms_actuelles.add("projets.creer")
    fab.definir_permissions(role_cp, perms_actuelles)

    client_cp = fab.client_pour(cp)
    r = client_cp.post(fab.url_projets(), fab.corps_projet("Projet Nouveau CP"), format="json")
    assert r.status_code == 201, f"CP avec projets.creer doit pouvoir créer un projet, reçu {r.status_code}"
    projet_id = r.data["id"]

    # Le projet est visible dans la liste GET /projets/
    r_list = client_cp.get(fab.url_projets())
    assert r_list.status_code == 200
    items = r_list.data.get("results", r_list.data) if isinstance(r_list.data, dict) else r_list.data
    ids_projets = [p["id"] for p in items]
    assert projet_id in ids_projets, "Le créateur doit voir son projet dans GET /projets/"

    # Vérification de l'affectation active créée pour le CP
    with fab._schema():
        aff = AffectationProjet.objects.filter(projet_id=projet_id, utilisateur=cp).first()
        assert aff is not None, "Une AffectationProjet doit être créée automatiquement pour le CP"
        assert aff.est_actif is True, "L'affectation doit être active"
        # Règle L5-8 : role_projet vide et projet.chef_projet non modifié
        assert aff.role_projet in ("", None), f"role_projet doit être vide, trouvé: {aff.role_projet}"

        p_db = Projet.objects.get(pk=projet_id)
        assert p_db.chef_projet_id != cp.pk, "Le champ projet.chef_projet ne doit pas être assigné automatiquement"


@NOUVEAU
def test_e04_cp_cree_deux_projets_deux_affectations_distinctes(fab):
    """[E-04] Si le même CP avec projets.creer crée deux projets, deux affectations distinctes sont créées."""
    from apps.projets.models import AffectationProjet

    cp = fab.acteur("CP")
    role_cp = cp.role
    perms = set(fab.permissions_de(cp))
    perms.add("projets.creer")
    fab.definir_permissions(role_cp, perms)

    client_cp = fab.client_pour(cp)
    r1 = client_cp.post(fab.url_projets(), fab.corps_projet("Projet Alpha"), format="json")
    assert r1.status_code == 201
    p1_id = r1.data["id"]

    r2 = client_cp.post(fab.url_projets(), fab.corps_projet("Projet Beta"), format="json")
    assert r2.status_code == 201
    p2_id = r2.data["id"]

    with fab._schema():
        aff1 = AffectationProjet.objects.filter(projet_id=p1_id, utilisateur=cp, est_actif=True).first()
        aff2 = AffectationProjet.objects.filter(projet_id=p2_id, utilisateur=cp, est_actif=True).first()
        assert aff1 is not None and aff2 is not None
        assert aff1.pk != aff2.pk
        assert aff1.projet_id != aff2.projet_id
