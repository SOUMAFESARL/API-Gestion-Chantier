"""Tests pour l'API des rôles dans les paramètres (/api/v1/parametres/roles/)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import (
    ModuleChoix,
    NiveauAcces,
    RoleGlobal,
    StatutUtilisateur,
)

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def admin_user(db):
    """Administrateur délégué (AD), is_owner=False."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="ad.param.roles@demo.ci",
            defaults={
                "nom": "Admin",
                "prenom": "Param",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.ADMIN
        user.is_owner = False
        user.set_password(MOT_DE_PASSE)
        user.save()
        return user


@pytest.fixture
def dg_user(db):
    """Directeur Général (DG), is_owner=True."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.param.roles@demo.ci",
            defaults={
                "nom": "Directeur",
                "prenom": "General",
                "role_global": RoleGlobal.DIRECTEUR_GENERAL,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": True,
            },
        )
        user.role_global = RoleGlobal.DIRECTEUR_GENERAL
        user.is_owner = True
        user.set_password(MOT_DE_PASSE)
        user.save()
        return user


@pytest.fixture
def collaborateur_user(db):
    """Collaborateur sans droits d'administration (Conducteur de travaux)."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="ct.param.roles@demo.ci",
            defaults={
                "nom": "Conducteur",
                "prenom": "Travaux",
                "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.CONDUCTEUR_TRAVAUX
        user.is_owner = False
        user.set_password(MOT_DE_PASSE)
        user.save()
        return user


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_get_parametres_roles_liste(client_tenant, collaborateur_user):
    """Tout collaborateur authentifié peut lister les rôles dans les paramètres."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

    client = _auth(client_tenant, collaborateur_user)
    rep = client.get("/api/v1/parametres/roles/")
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert len(data) >= 7
    premier_role = data[0]
    assert "code" in premier_role
    assert "permissions_modules" in premier_role
    assert "nb_utilisateurs" in premier_role


@pytest.mark.django_db
def test_post_parametres_roles_creer_par_admin(client_tenant, admin_user):
    """Un administrateur (AD) peut créer un rôle personnalisé avec sa matrice."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

    client = _auth(client_tenant, admin_user)
    payload = {
        "code": "CHEF_EQUIPE",
        "libelle": "Chef d'Équipe Maçonnerie",
        "description": "Responsable de l'équipe gros œuvre sur chantier",
        "permissions_modules": {
            ModuleChoix.CHANTIER: NiveauAcces.ECRITURE,
            ModuleChoix.QHSE: NiveauAcces.LECTURE,
            ModuleChoix.FINANCE: NiveauAcces.AUCUN,
        },
    }
    rep = client.post("/api/v1/parametres/roles/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["code"] == "CHEF_EQUIPE"
    assert data["libelle"] == "Chef d'Équipe Maçonnerie"
    assert data["permissions_modules"][ModuleChoix.CHANTIER] == NiveauAcces.ECRITURE
    assert data["permissions_modules"][ModuleChoix.QHSE] == NiveauAcces.LECTURE


@pytest.mark.django_db
def test_post_parametres_roles_creer_par_dg(client_tenant, dg_user):
    """Un Directeur Général (DG) peut créer un rôle personnalisé."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

    client = _auth(client_tenant, dg_user)
    payload = {
        "code": "AUDITEUR_EXTERNE",
        "libelle": "Auditeur Externe",
        "description": "Audit des comptes et chantiers",
        "permissions_modules": {
            ModuleChoix.FINANCE: NiveauAcces.LECTURE,
            ModuleChoix.PILOTAGE: NiveauAcces.LECTURE,
        },
    }
    rep = client.post("/api/v1/parametres/roles/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    assert rep.json()["code"] == "AUDITEUR_EXTERNE"


@pytest.mark.django_db
def test_post_parametres_roles_refuse_aux_collaborateurs(client_tenant, collaborateur_user):
    """Un collaborateur non admin/DG reçoit 403 Forbidden sur la création."""
    client = _auth(client_tenant, collaborateur_user)
    rep = client.post(
        "/api/v1/parametres/roles/",
        {"code": "INTERDIT", "libelle": "Rôle Interdit"},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_modifier_permissions_role_en_post_et_patch(client_tenant, admin_user):
    """Un administrateur peut modifier les permissions d'un rôle existant via PATCH et POST."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_cc = Role.objects.get(code=RoleGlobal.CHEF_CHANTIER)

    client = _auth(client_tenant, admin_user)

    # 1. Modification via PATCH
    rep_patch = client.patch(
        f"/api/v1/parametres/roles/{role_cc.id}/",
        {
            "permissions_modules": {
                ModuleChoix.FINANCE: NiveauAcces.LECTURE,
            }
        },
        format="json",
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.json()["permissions_modules"][ModuleChoix.FINANCE] == NiveauAcces.LECTURE

    # 2. Modification via POST (supporté pour flexibilité frontend)
    rep_post = client.post(
        f"/api/v1/parametres/roles/{role_cc.id}/",
        {
            "permissions_modules": {
                ModuleChoix.FINANCE: NiveauAcces.ECRITURE,
            }
        },
        format="json",
    )
    assert rep_post.status_code == status.HTTP_200_OK
    assert rep_post.json()["permissions_modules"][ModuleChoix.FINANCE] == NiveauAcces.ECRITURE


@pytest.mark.django_db
def test_supprimer_role_avec_reassignation_par_admin(client_tenant, admin_user):
    """Un administrateur peut supprimer un rôle personnalisé avec substitution obligatoire."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_cible = Role.objects.get(code=RoleGlobal.CONDUCTEUR_TRAVAUX)
        role_custom = Role.objects.create(
            code="A_SUPPRIMER",
            libelle="Rôle Temporaire",
            est_systeme=False,
            est_actif=True,
        )

    client = _auth(client_tenant, admin_user)

    # Sans substitution -> 400
    rep_sans_subst = client.post(
        f"/api/v1/parametres/roles/{role_custom.id}/supprimer/",
        {},
        format="json",
    )
    assert rep_sans_subst.status_code == status.HTTP_400_BAD_REQUEST

    # Avec substitution -> 200
    rep_succes = client.post(
        f"/api/v1/parametres/roles/{role_custom.id}/supprimer/",
        {"role_substitution_id": str(role_cible.id)},
        format="json",
    )
    assert rep_succes.status_code == status.HTTP_200_OK
    assert rep_succes.json()["role_supprime"] == "A_SUPPRIMER"

    with schema_context(SCHEMA):
        role_custom.refresh_from_db()
        assert role_custom.est_actif is False
        assert role_custom.supprime_le is not None
