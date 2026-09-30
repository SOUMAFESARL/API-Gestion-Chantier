"""Tests d'intégration pour la gestion dynamique des modules par le Super Admin (CRUD & Propagation)."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Module, Permission, Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_CLIENT = "demo"
HOTE_PLATEFORME = "localhost"


@pytest.fixture
def superuser_admin(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="super.admin@ccd-digital.ci").delete()
        return Utilisateur.objects.create_superuser(
            email="super.admin@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Admin",
            prenom="Plateforme",
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
        Utilisateur.tous_objets.filter(email="simple.user@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="simple.user@ccd-digital.ci",
            password="UserPassword123!",
            nom="Simple",
            prenom="User",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
            is_staff=False,
            is_superuser=False,
        )


@pytest.mark.django_db
def test_lister_modules_super_admin(client_admin, user_non_admin):
    """Vérifie la consultation des modules et le contrôle d'accès Super Admin."""
    # 1. Super Admin -> 200 OK
    rep = client_admin.get("/api/v1/admin/modules/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert isinstance(data, list)

    # 2. Utilisateur standard -> 403 Interdit
    client_user = APIClient()
    client_user.force_authenticate(user=user_non_admin)
    rep_user = client_user.get("/api/v1/admin/modules/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep_user.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_creer_module_et_propagation_multi_tenant(client_admin):
    """Création d'un module et vérification de la propagation dans le tenant client."""
    # Préparer les rôles par défaut dans le tenant demo
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    # Création du module par le Super Admin
    payload = {
        "code": "materiel",
        "libelle": "Gestion du Matériel et Engins",
        "description": "Suivi du parc d'engins et outillage de chantier",
        "ordre": 6,
        "icone": "truck",
        "est_actif": True,
    }
    rep = client_admin.post("/api/v1/admin/modules/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["code"] == "materiel"
    module_id = data["id"]

    # 1. Vérification dans public
    with schema_context(get_public_schema_name()):
        mod_pub = Module.objects.get(id=module_id, supprime_le__isnull=True)
        assert mod_pub.code == "materiel"

    # 2. Vérification dans le tenant demo
    with schema_context(SCHEMA_CLIENT):
        mod_tenant = Module.objects.get(code="materiel", supprime_le__isnull=True)
        assert mod_tenant.libelle == "Gestion du Matériel et Engins"

        # Invariant : Le Directeur Général a TOUTES les permissions disponibles
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        rmp_dg = RoleModulePermission.objects.get(role=role_dg, module=mod_tenant)
        all_perms_count = Permission.objects.filter(est_actif=True, supprime_le__isnull=True).count()
        assert rmp_dg.permissions.count() == all_perms_count

        # Invariant Zero-Trust : Le Chef de Chantier a un tableau vide [] de permissions
        role_cc = Role.objects.get(code=RoleGlobal.CHEF_CHANTIER)
        rmp_cc = RoleModulePermission.objects.get(role=role_cc, module=mod_tenant)
        assert rmp_cc.permissions.count() == 0


@pytest.mark.django_db
def test_modifier_module_et_propagation(client_admin):
    """Modification d'un module par le Super Admin et répercussion dans le tenant."""
    # Créer le module
    payload = {
        "code": "securite",
        "libelle": "Sécurité HSE",
        "description": "Contrôles hygiène et sécurité",
        "ordre": 7,
        "icone": "shield",
    }
    rep_create = client_admin.post("/api/v1/admin/modules/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    assert rep_create.status_code == status.HTTP_201_CREATED
    module_id = rep_create.json()["id"]

    # Modification
    patch_payload = {
        "libelle": "Qualité, Hygiène et Sécurité (QHSE)",
        "description": "Politique globale QHSE",
        "ordre": 8,
    }
    rep_patch = client_admin.patch(
        f"/api/v1/admin/modules/{module_id}/",
        patch_payload,
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.json()["libelle"] == "Qualité, Hygiène et Sécurité (QHSE)"

    # Vérification dans le tenant demo
    with schema_context(SCHEMA_CLIENT):
        mod_tenant = Module.objects.get(code="securite", supprime_le__isnull=True)
        assert mod_tenant.libelle == "Qualité, Hygiène et Sécurité (QHSE)"
        assert mod_tenant.ordre == 8


@pytest.mark.django_db
def test_supprimer_module_soft_delete(client_admin):
    """Suppression logique (soft-delete) d'un module par le Super Admin."""
    payload = {
        "code": "test_del",
        "libelle": "Module Temporaire",
    }
    rep_create = client_admin.post("/api/v1/admin/modules/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
    module_id = rep_create.json()["id"]

    # Suppression
    rep_del = client_admin.delete(f"/api/v1/admin/modules/{module_id}/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep_del.status_code == status.HTTP_200_OK

    # Vérification dans public : soft delete actif
    with schema_context(get_public_schema_name()):
        mod_pub = Module.tous_objets.get(id=module_id)
        assert mod_pub.est_actif is False
        assert mod_pub.supprime_le is not None

    # Vérification dans tenant demo : soft delete propagé
    with schema_context(SCHEMA_CLIENT):
        mod_tenant = Module.tous_objets.get(code="test_del")
        assert mod_tenant.est_actif is False
        assert mod_tenant.supprime_le is not None
