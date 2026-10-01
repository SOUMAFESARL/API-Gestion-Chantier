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
def test_creer_permission_et_propagation_ciblee_dg_admin(client_admin):
    """Création d'une permission avec modules cibles et auto-attribution sélective aux rôles de direction."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    payload = {
        "code": "AUDIT",
        "libelle": "Audit et Inspection",
        "description": "Capacité d'audit et d'inspection contradictoire",
        "ordre": 5,
        "est_actif": True,
        "modules": ["chantier", "ged"],
    }
    rep = client_admin.post("/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["code"] == "AUDIT"
    assert "modules_codes" in data
    assert sorted(data["modules_codes"]) == ["chantier", "ged"]
    perm_id = data["id"]

    # 1. Vérification dans public
    with schema_context(get_public_schema_name()):
        p_pub = Permission.objects.get(id=perm_id, supprime_le__isnull=True)
        assert p_pub.code == "AUDIT"
        assert set(p_pub.modules.values_list("code", flat=True)) == {"chantier", "ged"}

    # 2. Vérification dans le tenant demo : auto-attribuée à DG UNIQUEMENT sur 'chantier' et 'ged'
    with schema_context(SCHEMA_CLIENT):
        p_tenant = Permission.objects.get(code="AUDIT", supprime_le__isnull=True)
        assert set(p_tenant.modules.values_list("code", flat=True)) == {"chantier", "ged"}

        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        for rmp in RoleModulePermission.objects.filter(role=role_dg):
            if rmp.module.code in ["chantier", "ged"]:
                assert rmp.permissions.filter(code="AUDIT").exists()
            else:
                assert not rmp.permissions.filter(code="AUDIT").exists()


@pytest.mark.django_db
def test_creer_permission_sans_modules_zero_propagation(client_admin):
    """Création d'une permission sans module : elle n'est injectée dans aucun RoleModulePermission."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    payload = {
        "code": "SIGNER_CONTRAT",
        "libelle": "Signature de Contrat",
        "description": "Droit de signature juridique",
        "modules": [],
    }
    rep = client_admin.post("/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_201_CREATED
    perm_id = rep.json()["id"]

    with schema_context(SCHEMA_CLIENT):
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        for rmp in RoleModulePermission.objects.filter(role=role_dg):
            assert not rmp.permissions.filter(code="SIGNER_CONTRAT").exists()


@pytest.mark.django_db
def test_affecter_modules_a_posteriori_et_revocation(client_admin):
    """Le Super Admin décide a posteriori d'affecter des modules, puis en retire un (révocation)."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    # 1. Création sans module
    rep_create = client_admin.post(
        "/api/v1/admin/permissions/",
        {"code": "METTRE_EN_LIGNE", "libelle": "Mettre en ligne"},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    perm_id = rep_create.json()["id"]

    # 2. Affectation a posteriori : [chantier, ged]
    rep_affect = client_admin.post(
        f"/api/v1/admin/permissions/{perm_id}/modules/",
        {"modules": ["chantier", "ged"]},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_affect.status_code == status.HTTP_200_OK
    assert sorted(rep_affect.json()["modules_codes"]) == ["chantier", "ged"]

    with schema_context(SCHEMA_CLIENT):
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        rmp_chantier = RoleModulePermission.objects.get(role=role_dg, module__code="chantier")
        rmp_ged = RoleModulePermission.objects.get(role=role_dg, module__code="ged")
        rmp_projets = RoleModulePermission.objects.get(role=role_dg, module__code="projets")

        assert rmp_chantier.permissions.filter(code="METTRE_EN_LIGNE").exists()
        assert rmp_ged.permissions.filter(code="METTRE_EN_LIGNE").exists()
        assert not rmp_projets.permissions.filter(code="METTRE_EN_LIGNE").exists()

    # 3. Retrait du module 'ged' : seul 'chantier' est conservé
    rep_retrait = client_admin.post(
        f"/api/v1/admin/permissions/{perm_id}/modules/",
        {"modules": ["chantier"]},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_retrait.status_code == status.HTTP_200_OK
    assert rep_retrait.json()["modules_codes"] == ["chantier"]

    with schema_context(SCHEMA_CLIENT):
        rmp_chantier = RoleModulePermission.objects.get(role=role_dg, module__code="chantier")
        rmp_ged = RoleModulePermission.objects.get(role=role_dg, module__code="ged")

        # 'chantier' conserve la permission
        assert rmp_chantier.permissions.filter(code="METTRE_EN_LIGNE").exists()
        # 'ged' a été révoqué !
        assert not rmp_ged.permissions.filter(code="METTRE_EN_LIGNE").exists()


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
