"""Tests d'intégration pour la gestion dynamique des autorisations par le Super Admin."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.catalogue.models import CataloguePermission
from apps.core.droits import permissions_effectives
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
    for c in ["projets.lire", "projets.creer", "chantier.lire", "chantier.valider"]:
        assert c in codes

    # Non super admin -> 403
    client_user = APIClient()
    client_user.force_authenticate(user=user_non_admin)
    rep_user = client_user.get("/api/v1/admin/permissions/", HTTP_HOST=HOTE_PLATEFORME)
    assert rep_user.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_creer_permission_et_propagation_ciblee_dg_admin(client_admin):
    """Création/rétablissement d'une permission et respect de A-05 (aucun rôle stocké injecté)."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.get(code="chantier.valider")
        perm_id = perm.id

    # On supprime logiquement via l'API pour nettoyer les liaisons
    client_admin.delete(f"/api/v1/admin/permissions/{perm_id}/", HTTP_HOST=HOTE_PLATEFORME)

    payload = {
        "code": "chantier.valider",
        "libelle": "Validation des rapports",
        "description": "Validation contradictoire des rapports",
        "ordre": 5,
        "est_actif": True,
        "modules": ["chantier"],
    }
    rep = client_admin.post(
        "/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME
    )
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["code"] == "chantier.valider"
    assert "modules_codes" in data
    assert sorted(data["modules_codes"]) == ["chantier"]
    assert str(data["id"]) == str(perm_id)

    # 1. Vérification dans public
    with schema_context(get_public_schema_name()):
        p_pub = CataloguePermission.objects.get(id=perm_id, supprime_le__isnull=True)
        assert p_pub.code == "chantier.valider"
        assert set(p_pub.modules.values_list("code", flat=True)) == {"chantier"}

    # 2. Vérification tenant demo : respect de A-05, et DG a les droits via permissions_effectives
    with schema_context(SCHEMA_CLIENT):
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        for rmp in RoleModulePermission.objects.filter(role=role_dg):
            assert not rmp.permissions_catalogue.filter(code="chantier.valider").exists()

        u_dg = Utilisateur.objects.filter(role=role_dg, supprime_le__isnull=True).first()
        if u_dg:
            perms_dg = permissions_effectives(u_dg)
            assert "chantier.valider" in [p.lower() for p in perms_dg]


@pytest.mark.django_db
def test_creer_permission_sans_modules_zero_propagation(client_admin):
    """Création d'une permission sans module : rattachée à son module sans injection dans rôles."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.get(code="projets.affecter_membres")
        perm_id = perm.id

    client_admin.delete(f"/api/v1/admin/permissions/{perm_id}/", HTTP_HOST=HOTE_PLATEFORME)

    payload = {
        "code": "projets.affecter_membres",
        "libelle": "Affecter des membres",
        "description": "Affectation des équipes",
        "modules": [],
    }
    rep = client_admin.post(
        "/api/v1/admin/permissions/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME
    )
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert str(data["id"]) == str(perm_id)

    with schema_context(SCHEMA_CLIENT):
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        for rmp in RoleModulePermission.objects.filter(role=role_dg):
            assert not rmp.permissions_catalogue.filter(code="projets.affecter_membres").exists()


@pytest.mark.django_db
def test_affecter_modules_a_posteriori_et_revocation(client_admin):
    """Le Super Admin décide a posteriori d'affecter des modules, puis en retire un (révocation)."""
    with schema_context(SCHEMA_CLIENT):
        initialiser_roles_par_defaut()

    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.get(
            code="projets.gerer_equipes", supprime_le__isnull=True
        )
        perm_id = perm.id

    # 1. Retrait du module projets : la permission n'est plus attachée à aucun module
    rep_detacher = client_admin.post(
        f"/api/v1/admin/permissions/{perm_id}/modules/",
        {"modules": []},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_detacher.status_code == status.HTTP_200_OK
    assert rep_detacher.json()["modules_codes"] == []

    # 2. Affectation a posteriori : [projets]
    rep_affect = client_admin.post(
        f"/api/v1/admin/permissions/{perm_id}/modules/",
        {"modules": ["projets"]},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_affect.status_code == status.HTTP_200_OK
    assert sorted(rep_affect.json()["modules_codes"]) == ["projets"]

    # Tentative de rattachement à un mauvais module -> 400 (D2)
    rep_bad = client_admin.post(
        f"/api/v1/admin/permissions/{perm_id}/modules/",
        {"modules": ["chantier"]},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_bad.status_code == status.HTTP_400_BAD_REQUEST

    # On attribue manuellement la permission au CP dans le tenant demo
    with schema_context(SCHEMA_CLIENT):
        role_cp = Role.objects.get(code=RoleGlobal.CONDUCTEUR_TRAVAUX)
        rmp_projets = RoleModulePermission.objects.get(role=role_cp, module__code="projets")
        perm_cat = CataloguePermission.objects.get(id=perm_id)
        rmp_projets.permissions_catalogue.add(perm_cat)
        assert rmp_projets.permissions_catalogue.filter(id=perm_id).exists()

    # 3. Retrait du module : révocation de tous les rôles sur ce module
    rep_retrait = client_admin.post(
        f"/api/v1/admin/permissions/{perm_id}/modules/",
        {"modules": []},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_retrait.status_code == status.HTTP_200_OK
    assert rep_retrait.json()["modules_codes"] == []

    with schema_context(SCHEMA_CLIENT):
        rmp_projets.refresh_from_db()
        assert not rmp_projets.permissions_catalogue.filter(id=perm_id).exists()


@pytest.mark.django_db
def test_modifier_permission(client_admin):
    """Modification des métadonnées d'une permission."""
    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.get(
            code="projets.resilier_archiver", supprime_le__isnull=True
        )
        perm_id = perm.id

    rep_patch = client_admin.patch(
        f"/api/v1/admin/permissions/{perm_id}/",
        {"libelle": "Résilier / archiver définitivement"},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.json()["libelle"] == "Résilier / archiver définitivement"

    with schema_context(get_public_schema_name()):
        p_pub = CataloguePermission.objects.get(id=perm_id, supprime_le__isnull=True)
        assert p_pub.libelle == "Résilier / archiver définitivement"


@pytest.mark.django_db
def test_supprimer_permission_soft_delete(client_admin):
    """Suppression logique (soft delete) d'une permission."""
    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.filter(code="pilotage.voir_montants").first()
        perm_id = perm.id

    rep_del = client_admin.delete(
        f"/api/v1/admin/permissions/{perm_id}/", HTTP_HOST=HOTE_PLATEFORME
    )
    assert rep_del.status_code == status.HTTP_200_OK

    with schema_context(get_public_schema_name()):
        p_pub = CataloguePermission.tous_objets.get(id=perm_id)
        assert p_pub.est_actif is False
        assert p_pub.supprime_le is not None
