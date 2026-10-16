"""Tests d'acceptation pour la règle G-02 (Compatibilité du contrat GET /profil/ et autorité serveur)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role, RoleModulePermission
from apps.catalogue.models import CataloguePermission

pytestmark = pytest.mark.django_db


def test_g02_profil_dg_ad_cp_personnalise_forme(fab):
    """[G-02] Pour DG, AD, CP et personnalisé, /profil/ contient role_global et permissions."""
    perso = fab.creer_role_personnalise("ROLE_FORME", "Rôle Forme")
    roles_a_tester = ["DG", "AD", "CP", "ROLE_FORME"]

    for code in roles_a_tester:
        user = fab.utilisateur_avec_role(code, email=f"user.forme.{code.lower()}@demo.ci")
        client = fab.client_pour(user)
        rep = client.get("/api/v1/auth/profil/")
        assert rep.status_code == status.HTTP_200_OK

        data = rep.data
        assert "role_global" in data
        assert isinstance(data["role_global"], str)

        assert "permissions" in data
        assert isinstance(data["permissions"], list)


def test_g02_role_global_est_l_alias_du_role(fab):
    """[G-02] role_global dans /profil/ est l'alias en lecture seule du rôle souverain pour chaque rôle système."""
    for code in ["DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"]:
        user = fab.utilisateur_avec_role(code, email=f"user.alias.{code.lower()}@demo.ci")
        client = fab.client_pour(user)
        rep = client.get("/api/v1/auth/profil/")
        assert rep.status_code == status.HTTP_200_OK
        assert rep.data.get("role_global") == code


def test_g02_role_global_role_personnalise(fab):
    """[G-02] Pour un rôle personnalisé, role_global renvoie le code du rôle personnalisé."""
    perso = fab.creer_role_personnalise("MACON_CHEF", "Chef Maçon")
    user = fab.utilisateur_avec_role("MACON_CHEF", email="macon.profil@demo.ci")
    client = fab.client_pour(user)
    rep = client.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data.get("role_global") == "MACON_CHEF"


def test_g02_permissions_exactes_exposees(fab):
    """[G-02] Les permissions exposées dans /profil/ correspondent aux permissions effectives du rôle."""
    role = fab.creer_role_personnalise("ROLE_HAB_LIRE", "Hab Lire")
    with schema_context("demo"):
        p_lire = CataloguePermission.objects.filter(code="chantier.lire", est_actif=True).first()
        if p_lire:
            from apps.accounts.models import Module
            mod_chantier = Module.objects.get(code="chantier")
            rmp, _ = RoleModulePermission.objects.get_or_create(role=role, module=mod_chantier)
            rmp.permissions_catalogue.set([p_lire])

    user = fab.utilisateur_avec_role("ROLE_HAB_LIRE", email="user.hab.lire@demo.ci")
    client = fab.client_pour(user)
    rep = client.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = rep.data.get("permissions", [])
    assert "chantier.lire" in perms
    assert "chantier.rediger" not in perms


def test_g02_limite_connue_valider_seul(fab):
    """[G-02] Un rôle n'ayant que chantier.valider n'a ni chantier.lire ni chantier.rediger dans permissions."""
    role = fab.creer_role_personnalise("ROLE_HAB_VAL", "Hab Valider")
    with schema_context("demo"):
        p_val = CataloguePermission.objects.filter(code="chantier.valider", est_actif=True).first()
        if p_val:
            from apps.accounts.models import Module
            mod_chantier = Module.objects.get(code="chantier")
            rmp, _ = RoleModulePermission.objects.get_or_create(role=role, module=mod_chantier)
            rmp.permissions_catalogue.set([p_val])

    user = fab.utilisateur_avec_role("ROLE_HAB_VAL", email="user.hab.val@demo.ci")
    client = fab.client_pour(user)
    rep = client.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = rep.data.get("permissions", [])
    assert "chantier.valider" in perms
    assert "chantier.lire" not in perms
    assert "chantier.rediger" not in perms


def test_g02_aucune_permission_pour_module_inactif(fab):
    """[G-02] Un module inactif pour l'entreprise n'expose aucune permission dans /profil/."""
    with schema_context("demo"):
        from apps.accounts.models import Module
        mod_ged = Module.objects.filter(code="ged").first()
        if mod_ged:
            mod_ged.est_actif = False
            mod_ged.save()

    user = fab.utilisateur_avec_role("CP", email="cp.mod.inactif@demo.ci")
    client = fab.client_pour(user)
    rep = client.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = rep.data.get("permissions", [])
    assert not any(p.startswith("ged.") for p in perms)


def test_g02_role_global_non_ecrivable_via_profil(fab):
    """[G-02] Tenter d'écraser role_global via PATCH /profil/ est ignoré sans modifier le rôle de l'utilisateur."""
    user = fab.utilisateur_avec_role("CP", email="cp.patch.profil@demo.ci")
    client = fab.client_pour(user)
    rep = client.patch("/api/v1/auth/profil/", {"role_global": "ADMIN"}, format="json")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data.get("role_global") == "CP"


def test_g02_serveur_autorite(fab):
    """[G-02] Le serveur reste l'autorité : un utilisateur sans la permission requise reçoit 403."""
    user = fab.utilisateur_avec_role("CC", email="cc.sans.droit@demo.ci")
    client = fab.client_pour(user)
    # Tenter une action réservée à l'administration
    rep = client.post("/api/v1/parametres/roles/", {"code": "ROLE_PIRATE", "libelle": "Pirate"}, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN
