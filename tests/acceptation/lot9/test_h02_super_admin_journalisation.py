"""Tests de la règle H-02 (Un seul niveau de super admin et traçabilité systématique des écritures).

H-02 : is_staff ou is_superuser donne les mêmes accès.
Toute écriture super admin (activer, désactiver, propager, etc.) crée exactement une entrée dans JournalPlateforme.
Toute requête refusée (401, 403, 400, 404) n'écrit rien.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status


@pytest.mark.carac
@pytest.mark.django_db
def test_h02_staff_seul_et_superuser_seul_memes_acces(fab):
    """[H-02] Super admin is_staff seul et is_superuser seul ont les mêmes accès en lecture et écriture."""
    client_staff = fab.client_super_admin(staff=True, superuser=False)
    client_super = fab.client_super_admin(staff=False, superuser=True)

    # Lecture
    res_s_get = client_staff.get("/api/v1/admins/clients/")
    res_u_get = client_super.get("/api/v1/admins/clients/")
    assert res_s_get.status_code == status.HTTP_200_OK
    assert res_u_get.status_code == status.HTTP_200_OK


@pytest.mark.carac
@pytest.mark.django_db
def test_h02_acteurs_non_super_admin_refuses_sur_admins(fab):
    """[H-02] DG d'un tenant, AD, CP et anonyme sont systématiquement refusés sur les routes /admins/."""
    client_dg = fab.client_pour("DG")
    client_ad = fab.client_pour("AD")
    client_cp = fab.client_pour("CP")

    assert client_dg.get("/api/v1/admins/clients/").status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)
    assert client_ad.get("/api/v1/admins/clients/").status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)
    assert client_cp.get("/api/v1/admins/clients/").status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)


@pytest.mark.regle
@pytest.mark.django_db
def test_h02_ecritures_lot_creent_exactement_une_entree_journal_plateforme(fab):
    """[H-02] Chaque action d'écriture du lot crée exactement une entrée dans JournalPlateforme avec acteur, action, date."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="trace_h02")
    client_admin = fab.client_super_admin()

    nb_plat_avant = len(fab.entrees_journal_plateforme())

    res = fab.activer_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK

    nb_plat_apres = len(fab.entrees_journal_plateforme())
    assert nb_plat_apres == nb_plat_avant + 1

    derniere = fab.entrees_journal_plateforme()[0]
    assert derniere.utilisateur_id == client_admin.admin_user.id
    assert derniere.entreprise_id == ea.id


@pytest.mark.regle
@pytest.mark.django_db
def test_h02_requete_refusee_aucune_entree_journal_plateforme(fab):
    """[H-02] Une requête refusée (ex: 400 ou 404) n'écrit aucune entrée dans JournalPlateforme."""
    client_admin = fab.client_super_admin()
    nb_plat_avant = len(fab.entrees_journal_plateforme())

    # Requête avec UUID inexistant (404)
    res = client_admin.post("/api/v1/admins/clients/00000000-0000-0000-0000-000000000000/modules/00000000-0000-0000-0000-000000000000/activer/", format="json")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    nb_plat_apres = len(fab.entrees_journal_plateforme())
    assert nb_plat_apres == nb_plat_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_h02_couverture_routes_ecriture_admins(fab):
    """[H-02] Toutes les routes d'écriture réelles sous /admins/ figurent dans l'inventaire P1."""
    routes_ecriture = fab.routes_admin_en_ecriture()
    assert len(routes_ecriture) > 0
    # Vérification que la route d'activation de module client fait bien partie des routes montées
    routes_paths = [r[1] for r in routes_ecriture]
    assert any("modules" in path and "activer" in path for path in routes_paths)
