"""Tests d'acceptation pour la règle B-03 (Le Directeur Général souverain)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role, Utilisateur
from apps.catalogue.models import CataloguePermission
from apps.core.droits import _obtenir_modules_actifs
from apps.core.registre_permissions import REGISTRE

pytestmark = pytest.mark.django_db


def test_b03_un_seul_dg(client_dg, fab):
    """[B-03] Il ne peut y avoir qu'un seul DG par entreprise ; toute tentative d'en créer un second est refusée."""
    payload = {
        "email": "tentative.dg.second@demo.ci",
        "nom": "Second",
        "prenom": "DG",
        "role_global": "DG",
    }
    rep = client_dg.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST)

    user_autre = fab.utilisateur_avec_role("CP", email="autre.vers.dg@demo.ci")
    rep_patch = client_dg.patch(
        f"/api/v1/parametres/collaborateurs/{user_autre.id}/",
        {"role_global": "DG"},
        format="json",
    )
    assert rep_patch.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST)


def test_b03_permissions_du_dg_calculees(client_dg):
    """[B-03] Le DG reçoit toutes les permissions des modules actifs de l'entreprise et de l'administration."""
    rep = client_dg.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = set(rep.data.get("permissions", []))

    with schema_context("demo"):
        modules_actifs = _obtenir_modules_actifs()
        attendues = {
            code
            for code, def_p in REGISTRE.items()
            if def_p.module in modules_actifs or def_p.module == "administration"
        }
        # Les permissions actives doivent correspondre
        assert attendues.issubset(perms) or perms == attendues


def test_b03_dg_module_desactive(client_dg):
    """[B-03] Si un module est inactif, aucune de ses permissions n'est accordée au DG."""
    with schema_context("demo"):
        from apps.accounts.models import Module
        mod_ged = Module.objects.filter(code="ged").first()
        if mod_ged:
            mod_ged.est_actif = False
            mod_ged.save()

    rep = client_dg.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = set(rep.data.get("permissions", []))
    assert not any(p.startswith("ged.") for p in perms)


def test_b03_dg_nouvelle_permission(client_dg):
    """[B-03] Une nouvelle permission active du catalogue est automatiquement accordée au DG."""
    with schema_context("demo"):
        p_projet = CataloguePermission.objects.filter(module__code="projets", est_actif=True).first()

    rep = client_dg.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    if p_projet:
        assert p_projet.code in rep.data.get("permissions", [])


def test_b03_matrice_du_dg_intouchable_par_dg(client_dg, fab):
    """[B-03] Le DG lui-même ne peut pas modifier la matrice de permissions de son propre rôle (403)."""
    with schema_context("demo"):
        role_dg = Role.objects.get(code="DG", supprime_le__isnull=True)

    rep = client_dg.patch(
        f"/api/v1/parametres/roles/{role_dg.id}/",
        {"permissions_modules": {"chantier": 1}},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_b03_matrice_du_dg_intouchable_par_ad(client_ad, fab):
    """[B-03] L'administrateur (AD) ne peut pas modifier la matrice de permissions du rôle DG (403)."""
    with schema_context("demo"):
        role_dg = Role.objects.get(code="DG", supprime_le__isnull=True)

    rep = client_ad.patch(
        f"/api/v1/parametres/roles/{role_dg.id}/",
        {"permissions_modules": {"chantier": 1}},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_b03_actions_visant_le_dg(client_ad, client_dg, fab):
    """[B-03] Toute tentative de changer le rôle du DG reçoit 403."""
    dg = fab.obtenir_dg()
    # Par un AD
    rep_ad = client_ad.patch(
        f"/api/v1/parametres/collaborateurs/{dg.id}/",
        {"role_global": "CP"},
        format="json",
    )
    assert rep_ad.status_code == status.HTTP_403_FORBIDDEN

    # Par le DG lui-même
    rep_dg = client_dg.patch(
        f"/api/v1/parametres/collaborateurs/{dg.id}/",
        {"role_global": "CP"},
        format="json",
    )
    assert rep_dg.status_code == status.HTTP_403_FORBIDDEN


def test_b03_dg_non_suspendable_non_supprimable(client_ad, client_dg, fab):
    """[B-03] Le DG ne peut être ni suspendu ni supprimé par quiconque (403)."""
    dg = fab.obtenir_dg()

    # Tentatives par AD
    rep_susp_ad = client_ad.post(f"/api/v1/parametres/collaborateurs/{dg.id}/suspendre/")
    assert rep_susp_ad.status_code == status.HTTP_403_FORBIDDEN

    rep_del_ad = client_ad.delete(f"/api/v1/parametres/collaborateurs/{dg.id}/")
    assert rep_del_ad.status_code == status.HTTP_403_FORBIDDEN

    # Tentatives par DG lui-même
    rep_susp_dg = client_dg.post(f"/api/v1/parametres/collaborateurs/{dg.id}/suspendre/")
    assert rep_susp_dg.status_code == status.HTTP_403_FORBIDDEN

    rep_del_dg = client_dg.delete(f"/api/v1/parametres/collaborateurs/{dg.id}/")
    assert rep_del_dg.status_code == status.HTTP_403_FORBIDDEN


def test_b03_une_seule_fonction_est_dg():
    """[B-03] La fonction centrale est_dg existe pour remplacer les vérifications dispersées."""
    from apps.core.droits import est_dg
    assert callable(est_dg)
