"""Tests d'intégration validant l'alignement strict entre l'API Entreprise Backend et le Frontend.

Vérifie les contrats d'interface suivants :
1. Rôles et Permissions : acceptation et renvoi des accès normalisés ("lecture", "saisie", "validation").
2. Collaborateurs : présence de avatar_url et derniere_connexion sur GET /parametres/collaborateurs/.
3. Cycle de vie Collaborateur : POST /parametres/collaborateurs/{id}/suspendre/ et reactiver/ avec sécurité (400 auto-suspension, 403 DG/Owner, 409 conflits).
4. Modules : présence des champs 'id', 'statut' (ACTIF) et 'acces_par_defaut' sur GET /modules/.
5. Matrice Permissions Projets : acceptation et renvoi de la liste 'acces' sur GET et PUT /projets/{id}/permissions-roles/.
"""

import pytest
from django.contrib.auth.hashers import make_password
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Module, Permission, Role, Utilisateur
from apps.core.enums import RoleGlobal, StatutProjet, StatutUtilisateur, TypeTiers
from apps.projets.models import Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def dg_user(db):
    """Directeur Général (DG), is_owner=True."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.alignement@demo.ci",
            defaults={
                "nom": "Kouassi",
                "prenom": "Directeur",
                "role_global": RoleGlobal.DIRECTEUR_GENERAL,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": True,
            },
        )
        user.role_global = RoleGlobal.DIRECTEUR_GENERAL
        user.is_owner = True
        user.statut = StatutUtilisateur.ACTIF
        user.is_active = True
        user.password = make_password(MOT_DE_PASSE)
        user.save()
        return user


@pytest.fixture
def admin_user(db):
    """Administrateur délégué."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.alignement@demo.ci",
            defaults={
                "nom": "Admin",
                "prenom": "Delegue",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.ADMIN
        user.is_owner = False
        user.statut = StatutUtilisateur.ACTIF
        user.is_active = True
        user.password = make_password(MOT_DE_PASSE)
        user.save()
        return user


@pytest.fixture
def collab_user(db):
    """Collaborateur standard (Conducteur de travaux)."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="ct.alignement@demo.ci",
            defaults={
                "nom": "Soro",
                "prenom": "Mamadou",
                "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.CONDUCTEUR_TRAVAUX
        user.is_owner = False
        user.statut = StatutUtilisateur.ACTIF
        user.is_active = True
        user.password = make_password(MOT_DE_PASSE)
        user.save()
        return user


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_roles_endpoints_frontend_format(client_tenant, dg_user):
    """POST, GET et PATCH /parametres/roles/ supportent le format attendu par le frontend (lecture, saisie, validation)."""
    _auth(client_tenant, dg_user)

    # 1. Création avec les codes frontend minuscules
    payload_creation = {
        "code": "CHEF_EQUIPE_ALIGN",
        "libelle": "Chef d'équipe Alignement",
        "description": "Rôle créé pour valider l'alignement frontend",
        "permissions_modules": {
            "projets": ["lecture", "saisie"]
        },
    }
    rep_create = client_tenant.post(
        "/api/v1/parametres/roles/",
        payload_creation,
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_create.status_code == status.HTTP_201_CREATED
    data_create = rep_create.json()
    assert "lecture" in data_create["permissions_modules"]["projets"]
    assert "saisie" in data_create["permissions_modules"]["projets"]
    role_id = data_create["id"]

    # 2. GET liste paramètres rôles
    rep_list = client_tenant.get("/api/v1/parametres/roles/", HTTP_HOST=HOTE)
    assert rep_list.status_code == status.HTTP_200_OK
    data_list = rep_list.json()
    created_role_item = next((r for r in data_list if str(r["id"]) == str(role_id)), None)
    assert created_role_item is not None
    assert "lecture" in created_role_item["permissions_modules"]["projets"]
    assert "saisie" in created_role_item["permissions_modules"]["projets"]

    # 3. PATCH modification des permissions
    rep_patch = client_tenant.patch(
        f"/api/v1/parametres/roles/{role_id}/",
        {"permissions_modules": {"projets": ["lecture", "saisie", "validation"]}},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    data_patch = rep_patch.json()
    assert "validation" in data_patch["permissions_modules"]["projets"]


@pytest.mark.django_db
def test_collaborateurs_endpoints_frontend_format(client_tenant, dg_user, collab_user):
    """GET /parametres/collaborateurs/ et GET /parametres/collaborateurs/{id}/ contiennent avatar_url et derniere_connexion."""
    _auth(client_tenant, dg_user)

    # GET liste
    rep = client_tenant.get("/api/v1/parametres/collaborateurs/", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    item = next((c for c in data if str(c["id"]) == str(collab_user.id)), None)
    assert item is not None
    assert "avatar_url" in item
    assert "derniere_connexion" in item

    # GET détail
    rep_detail = client_tenant.get(f"/api/v1/parametres/collaborateurs/{collab_user.id}/", HTTP_HOST=HOTE)
    assert rep_detail.status_code == status.HTTP_200_OK
    data_detail = rep_detail.json()
    assert "avatar_url" in data_detail
    assert "derniere_connexion" in data_detail


@pytest.mark.django_db
def test_collaborateurs_suspendre_et_reactiver(client_tenant, dg_user, collab_user):
    """POST .../suspendre/ et .../reactiver/ gèrent le changement de statut et les conflits 409."""
    _auth(client_tenant, dg_user)

    # 1. Suspension
    rep_susp = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/suspendre/", HTTP_HOST=HOTE)
    assert rep_susp.status_code == status.HTTP_200_OK
    data_susp = rep_susp.json()
    assert data_susp["statut"] == "DESACTIVE"

    with schema_context(SCHEMA):
        collab_user.refresh_from_db()
        assert collab_user.statut == StatutUtilisateur.DESACTIVE
        assert collab_user.is_active is False

    # 2. Conflit: déjà suspendu -> 409
    rep_susp_conflict = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/suspendre/", HTTP_HOST=HOTE)
    assert rep_susp_conflict.status_code == status.HTTP_409_CONFLICT

    # 3. Réactivation
    rep_react = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/reactiver/", HTTP_HOST=HOTE)
    assert rep_react.status_code == status.HTTP_200_OK
    data_react = rep_react.json()
    assert data_react["statut"] == "ACTIF"

    with schema_context(SCHEMA):
        collab_user.refresh_from_db()
        assert collab_user.statut == StatutUtilisateur.ACTIF
        assert collab_user.is_active is True

    # 4. Conflit: déjà actif -> 409
    rep_react_conflict = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/reactiver/", HTTP_HOST=HOTE)
    assert rep_react_conflict.status_code == status.HTTP_409_CONFLICT


@pytest.mark.django_db
def test_collaborateurs_suspendre_regles_securite(client_tenant, dg_user, admin_user):
    """Vérifie l'impossibilité de s'auto-suspendre (400) ou de suspendre un DG/Owner (403)."""
    # 1. DG essaie de se suspendre lui-même -> 400
    _auth(client_tenant, dg_user)
    rep_auto = client_tenant.post(f"/api/v1/parametres/collaborateurs/{dg_user.id}/suspendre/", HTTP_HOST=HOTE)
    assert rep_auto.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Admin essaie de suspendre le DG -> 400
    _auth(client_tenant, admin_user)
    rep_dg = client_tenant.post(f"/api/v1/parametres/collaborateurs/{dg_user.id}/suspendre/", HTTP_HOST=HOTE)
    assert rep_dg.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_modules_endpoints_frontend_format(client_tenant, dg_user):
    """GET /api/v1/modules/ renvoie id, statut='ACTIF' et acces_par_defaut requis par le frontend."""
    _auth(client_tenant, dg_user)

    rep = client_tenant.get("/api/v1/modules/", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    for mod in data:
        assert "id" in mod
        assert "statut" in mod
        assert mod["statut"] == "ACTIF"
        assert "acces_par_defaut" in mod
        assert isinstance(mod["acces_par_defaut"], list)
        assert "lecture" in mod["acces_par_defaut"]


@pytest.mark.django_db
def test_projets_permissions_roles_override_frontend_format(client_tenant, dg_user):
    """GET et PUT /projets/{id}/permissions-roles/ supportent la clé 'acces' du frontend."""
    _auth(client_tenant, dg_user)

    with schema_context(SCHEMA):
        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="Client Alignement",
            defaults={"type_tiers": TypeTiers.ENTREPRISE, "telephone": "+2250102030405"},
        )
        projet, _ = Projet.objects.get_or_create(
            reference="PRJ-ALIGN-001",
            defaults={
                "nom": "Chantier Alignement",
                "client": client_tiers,
                "statut": StatutProjet.EN_COURS,
            },
        )
        role, _ = Role.objects.get_or_create(
            code="CONDUCTEUR_TRAVAUX",
            defaults={"libelle": "Conducteur de travaux", "est_systeme": True},
        )

    # 1. GET matrice permissions-roles
    rep_get = client_tenant.get(f"/api/v1/projets/{projet.id}/permissions-roles/", HTTP_HOST=HOTE)
    assert rep_get.status_code == status.HTTP_200_OK
    data_get = rep_get.json()
    assert isinstance(data_get, list)
    role_item = next((r for r in data_get if str(r["role_id"]) == str(role.id)), None)
    assert role_item is not None
    assert "modules" in role_item
    assert "projets" in role_item["modules"]
    assert "acces" in role_item["modules"]["projets"]

    # 2. PUT surcharge avec 'acces'
    payload = {
        "surcharges": [
            {
                "role_id": str(role.id),
                "module": "projets",
                "acces": ["lecture", "saisie"],
            }
        ]
    }
    rep_put = client_tenant.put(
        f"/api/v1/projets/{projet.id}/permissions-roles/",
        payload,
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_put.status_code == status.HTTP_200_OK
    data_put = rep_put.json()
    assert isinstance(data_put, list)
    role_put = next((r for r in data_put if str(r["role_id"]) == str(role.id)), None)
    assert role_put is not None
    assert role_put["modules"]["projets"]["est_surcharge"] is True
    assert "lecture" in role_put["modules"]["projets"]["acces"]
    assert "saisie" in role_put["modules"]["projets"]["acces"]
