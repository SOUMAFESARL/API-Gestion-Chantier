"""Tests d'intégration pour la gestion dynamique des autorisations par le Super Admin."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_CLIENT = "demo"
HOTE_PLATEFORME = "localhost"


@pytest.fixture
def superuser_admin(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="super.perm.admin@ccd-digital.ci").delete()
        return Utilisateur.objects.create_superuser(
            email="super.perm.admin@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Admin",
            prenom="Permissions",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )


@pytest.fixture
def client_admin(superuser_admin):
    client = APIClient()
    client.force_authenticate(user=superuser_admin)
    return client


@pytest.fixture
def user_non_admin(db):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="simple.perm.user@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="simple.perm.user@ccd-digital.ci",
            password="UserPassword123!",
            nom="Simple",
            prenom="User",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
            is_staff=False,
            is_superuser=False,
        )


@pytest.mark.django_db
def test_lister_permissions_super_admin(client_admin, user_non_admin):
    """Vérifie la consultation des permissions et la restriction d'accès."""
    rep = client_admin.get("/api/v1/admin/permissions/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert isinstance(data, list)
    codes = [p["code"] for p in data]
    for c in ["LECTURE", "ECRITURE", "VALIDATION", "SUPPRESSION"]:
        assert c in codes

    # Non super admin -> 403
    client_user = APIClient()
    client_user.force_authenticate(user=user_non_admin)
    rep_user = client_user.get("/api/v1/admin/permissions/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep_user.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_creer_permission_et_propagation_dg_admin(client_admin):
    """Création d'une permission et auto-attribution aux rôles de direction dans les tenants."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    payload = {
        "code": "AUDIT",
        "libelle": "Audit et Inspection",
        "description": "Capacité d'audit et d'inspection contradictoire",
        "ordre": 5,
        "est_actif": True,
    }
    rep = client_admin.post("/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["code"] == "AUDIT"
    perm_id = data["id"]

    # 1. Vérification dans public
    with schema_context(get_public_schema_name()):
        p_pub = Permission.objects.get(id=perm_id, supprime_le__isnull=True)
        assert p_pub.code == "AUDIT"

    # 2. Vérification dans le tenant demo : auto-attribuée à DG et ADMIN
    with schema_context(SCHEMA_CLIENT):
        p_tenant = Permission.objects.get(code="AUDIT", supprime_le__isnull=True)
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        for rmp in RoleModulePermission.objects.filter(role=role_dg):
            assert rmp.permissions.filter(code="AUDIT").exists()


@pytest.mark.django_db
def test_modifier_permission(client_admin):
    """Modification des métadonnées d'une permission."""
    payload = {
        "code": "EXPORT_EXCEL",
        "libelle": "Export Excel",
        "description": "Export brut des données",
        "ordre": 6,
    }
    rep_create = client_admin.post("/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    perm_id = rep_create.json()["id"]

    rep_patch = client_admin.patch(
        f"/api/v1/admin/permissions/{perm_id}/",
        {"libelle": "Exportation Tableurs (Excel / CSV)"},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.json()["libelle"] == "Exportation Tableurs (Excel / CSV)"

    with schema_context(SCHEMA_CLIENT):
        p_tenant = Permission.objects.get(code="EXPORT_EXCEL", supprime_le__isnull=True)
        assert p_tenant.libelle == "Exportation Tableurs (Excel / CSV)"


@pytest.mark.django_db
def test_supprimer_permission_soft_delete(client_admin):
    """Suppression logique (soft delete) d'une permission."""
    payload = {
        "code": "PERM_TEMP",
        "libelle": "Permission Éphémère",
    }
    rep_create = client_admin.post("/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    perm_id = rep_create.json()["id"]

    rep_del = client_admin.delete(f"/api/v1/admin/permissions/{perm_id}/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep_del.status_code == status.HTTP_200_OK

    with schema_context(get_public_schema_name()):
        p_pub = Permission.tous_objets.get(id=perm_id)
        assert p_pub.est_actif is False
        assert p_pub.supprime_le is not None
