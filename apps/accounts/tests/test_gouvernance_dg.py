"""Tests de validation de la gouvernance DG vs Admin délégué — T-S1-01 (US-017).

Vérifie :
1. L'enrichissement du profil compact (is_dg, is_owner).
2. L'interdiction pour un admin délégué d'inviter ADMIN ou DG (403 action_interdite_delegue).
3. L'autorisation pour le DG / Owner d'inviter tout rôle.
4. La possibilité pour un admin délégué d'inviter des rôles opérationnels (CT, CP, etc.).
5. L'immutabilité du propriétaire / fondateur (suppression et désactivation interdites).
"""

import pytest
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def dg_owner(db):
    """Directeur Général et Propriétaire fondateur du tenant."""
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="dg.fondateur@demo.ci").delete()
        user = Utilisateur.objects.create_user(
            email="dg.fondateur@demo.ci",
            password="DgPassword123!",
            nom="Kouamé",
            prenom="Patrice",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        user.is_owner = True
        user.save(update_fields=["is_owner", "modifie_le"])
        yield user
        Invitation.objects.filter(emetteur=user).delete()
        Utilisateur.tous_objets.filter(pk=user.pk).delete()


@pytest.fixture
def admin_delegue(db):
    """Administrateur délégué (non-owner, non-DG)."""
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.delegue@demo.ci").delete()
        user = Utilisateur.objects.create_user(
            email="admin.delegue@demo.ci",
            password="DeleguePassword123!",
            nom="Yao",
            prenom="N'Goran",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        assert user.is_owner is False
        assert user.is_dg is False
        yield user
        Invitation.objects.filter(emetteur=user).delete()
        Utilisateur.tous_objets.filter(pk=user.pk).delete()


@pytest.mark.django_db
def test_profil_connexion_enrichi_dg_et_owner(dg_owner):
    """REC-S1-01-A : POST /api/v1/auth/token/ retourne is_dg: True et is_owner: True."""
    client = APIClient(headers={"host": HOTE})
    reponse = client.post(
        "/api/v1/auth/token/",
        {"email": "dg.fondateur@demo.ci", "mot_de_passe": "DgPassword123!"},
        format="json",
    )

    assert reponse.status_code == status.HTTP_200_OK
    assert "utilisateur" in reponse.data
    profil = reponse.data["utilisateur"]
    assert profil["email"] == "dg.fondateur@demo.ci"
    assert profil["role_global"] == "DG"
    assert profil["is_dg"] is True
    assert profil["is_owner"] is True
    assert "doit_changer_mot_de_passe" in profil


@pytest.mark.django_db
def test_endpoint_auth_profil(dg_owner, admin_delegue):
    """REC-S1-01-B : GET /api/v1/auth/profil/ retourne le profil complet."""
    client = APIClient(headers={"host": HOTE})

    # 1. Appel par le DG
    client.force_authenticate(user=dg_owner)
    rep_dg = client.get("/api/v1/auth/profil/")
    assert rep_dg.status_code == status.HTTP_200_OK
    assert rep_dg.data["id"] == str(dg_owner.pk)
    assert rep_dg.data["email"] == "dg.fondateur@demo.ci"
    assert rep_dg.data["role_global"] == "DG"
    assert rep_dg.data["is_dg"] is True
    assert rep_dg.data["is_owner"] is True

    # 2. Appel par l'admin délégué
    client.force_authenticate(user=admin_delegue)
    rep_admin = client.get("/api/v1/auth/profil/")
    assert rep_admin.status_code == status.HTTP_200_OK
    assert rep_admin.data["id"] == str(admin_delegue.pk)
    assert rep_admin.data["email"] == "admin.delegue@demo.ci"
    assert rep_admin.data["role_global"] == "AD"
    assert rep_admin.data["is_dg"] is False
    assert rep_admin.data["is_owner"] is False


@pytest.mark.django_db
def test_dg_owner_peut_inviter_admin_mais_pas_dg(dg_owner):
    """REC-S1-01-C : Le DG / Owner peut inviter des admins, mais le rôle DG est immuable et non attribuable."""
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=dg_owner)

    # Invitation d'un ADMIN (autorisée pour le DG)
    rep_admin = client.post(
        "/api/v1/invitations/",
        {"email": "nouvel.admin@demo.ci", "role_propose": "AD", "nom": "Konan"},
        format="json",
    )
    assert rep_admin.status_code == status.HTTP_201_CREATED
    assert rep_admin.data["role_propose"] == "AD"

    # Tentative d'invitation d'un second DG (strictement interdite : DG immuable et unique au fondateur)
    rep_dg = client.post(
        "/api/v1/invitations/",
        {"email": "co.dg@demo.ci", "role_propose": "DG", "nom": "Touré"},
        format="json",
    )
    assert rep_dg.status_code == status.HTTP_400_BAD_REQUEST
    assert rep_dg.data["erreur"]["code"] == "role_dg_non_attribuable"


@pytest.mark.django_db
def test_admin_delegue_interdit_inviter_admin_ou_dg(admin_delegue):
    """REC-S1-01-D : L'admin délégué ne peut ni inviter d'admin (403) ni de DG (400 rôle non attribuable)."""
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=admin_delegue)

    # 1. Tentative d'invitation rôle ADMIN (AD) -> 403 Seul le DG peut nommer un admin
    rep_ad = client.post(
        "/api/v1/invitations/",
        {"email": "tentative.admin@demo.ci", "role_propose": "AD", "nom": "Infiltré"},
        format="json",
    )
    assert rep_ad.status_code == status.HTTP_403_FORBIDDEN
    assert rep_ad.data["erreur"]["code"] == "action_interdite_delegue"
    assert (
        rep_ad.data["erreur"]["message"]
        == "Seul le Directeur Général peut inviter ou nommer un administrateur."
    )

    # 2. Tentative d'invitation rôle DG -> 400 Rôle DG non attribuable / immuable
    rep_dg = client.post(
        "/api/v1/invitations/",
        {"email": "tentative.dg@demo.ci", "role_propose": "DG", "nom": "Infiltré"},
        format="json",
    )
    assert rep_dg.status_code == status.HTTP_400_BAD_REQUEST
    assert rep_dg.data["erreur"]["code"] == "role_dg_non_attribuable"


@pytest.mark.django_db
def test_admin_delegue_peut_inviter_autres_roles(admin_delegue):
    """REC-S1-01-E : L'admin délégué peut parfaitement inviter des rôles opérationnels (CT, CP)."""
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=admin_delegue)

    rep_ct = client.post(
        "/api/v1/invitations/",
        {"email": "conducteur@demo.ci", "role_propose": "CT", "nom": "Soro"},
        format="json",
    )
    assert rep_ct.status_code == status.HTTP_201_CREATED
    assert rep_ct.data["role_propose"] == "CT"

    rep_cp = client.post(
        "/api/v1/invitations/",
        {"email": "chef.projet@demo.ci", "role_propose": "CP", "nom": "Bakayoko"},
        format="json",
    )
    assert rep_cp.status_code == status.HTTP_201_CREATED
    assert rep_cp.data["role_propose"] == "CP"


@pytest.mark.django_db
def test_immuabilite_owner(dg_owner):
    """REC-S1-01-F : Le Propriétaire fondateur ne peut être ni supprimé ni rétrogradé."""
    with schema_context(SCHEMA):
        # 1. Tentative de suppression directe
        with pytest.raises(ValidationError, match="ne peut pas être supprimé"):
            dg_owner.delete()

        # 2. Tentative de désactivation
        dg_owner.statut = StatutUtilisateur.DESACTIVE
        with pytest.raises(ValidationError, match="ne peut pas être désactivé"):
            dg_owner.save()

        # 3. Tentative de retrait du statut de propriétaire
        dg_owner.refresh_from_db()
        dg_owner.is_owner = False
        with pytest.raises(ValidationError, match="statut de Propriétaire est immuable"):
            dg_owner.save()
