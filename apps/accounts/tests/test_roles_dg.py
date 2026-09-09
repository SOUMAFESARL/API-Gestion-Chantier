"""Tests pour la gestion des rôles réservée au DG
et la suppression sécurisée avec réassignation (T-S1-10 / US-026).
"""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutUtilisateur,
    TypeTiers,
)
from apps.projets.models import AffectationProjet, Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def dg_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="dg.roles@demo.ci").delete()
        dg = Utilisateur.objects.create_user(
            email="dg.roles@demo.ci",
            password=MOT_DE_PASSE,
            nom="Kouamé",
            prenom="Patrice",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )
        yield dg
        AffectationProjet.tous_objets.all().delete()
        Projet.tous_objets.all().delete()
        Tiers.tous_objets.all().delete()
        Role.tous_objets.all().delete()
        Utilisateur.tous_objets.filter(email="adjoint@demo.ci").delete()
        Utilisateur.tous_objets.filter(pk=dg.pk).delete()


@pytest.fixture
def admin_delegue_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.delegue.roles@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.delegue.roles@demo.ci",
            password=MOT_DE_PASSE,
            nom="Yao",
            prenom="Adjoua",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_owner=False,
        )
        yield admin
        Utilisateur.tous_objets.filter(pk=admin.pk).delete()


@pytest.fixture
def conducteur_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="conducteur.roles@demo.ci").delete()
        ct = Utilisateur.objects.create_user(
            email="conducteur.roles@demo.ci",
            password=MOT_DE_PASSE,
            nom="Bakayoko",
            prenom="Moussa",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
            is_owner=False,
        )
        yield ct
        Utilisateur.tous_objets.filter(pk=ct.pk).delete()


def auth_client(client, user):
    rep = client.post(
        "/api/v1/auth/token/",
        {"email": user.email, "mot_de_passe": MOT_DE_PASSE, "origine": "WEB"},
        format="json",
    )
    token = rep.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_rec_s1_10_a_action_reservee_dg(
    client_tenant, dg_user, admin_delegue_user, conducteur_user
):
    """REC-S1-10-A : Seul le DG peut créer, modifier ou supprimer un rôle
    (403 action_reservee_dg pour les autres).
    """
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_vi = Role.objects.get(code=RoleGlobal.VISITEUR)

    # 1. Un conducteur de travaux tente de créer un rôle
    cl_ct = auth_client(client_tenant, conducteur_user)
    rep1 = cl_ct.post(
        "/api/v1/roles/",
        {"code": "TEST_CT", "libelle": "Test CT", "permissions_modules": {}},
        format="json",
    )
    assert rep1.status_code == status.HTTP_403_FORBIDDEN
    assert rep1.json()["erreur"]["code"] == "action_reservee_dg"

    # 2. Un administrateur délégué tente de créer un rôle
    cl_ad = auth_client(client_tenant, admin_delegue_user)
    rep2 = cl_ad.post(
        "/api/v1/roles/",
        {"code": "TEST_AD", "libelle": "Test AD", "permissions_modules": {}},
        format="json",
    )
    assert rep2.status_code == status.HTTP_403_FORBIDDEN
    assert rep2.json()["erreur"]["code"] == "action_reservee_dg"

    # 3. L'administrateur délégué tente de modifier un rôle existant
    rep3 = cl_ad.patch(
        f"/api/v1/roles/{role_vi.id}/",
        {"libelle": "Visiteur Modifié"},
        format="json",
    )
    assert rep3.status_code == status.HTTP_403_FORBIDDEN
    assert rep3.json()["erreur"]["code"] == "action_reservee_dg"

    # 4. L'administrateur délégué tente de supprimer un rôle
    rep4 = cl_ad.post(
        f"/api/v1/roles/{role_vi.id}/supprimer/",
        {"role_substitution_id": str(role_vi.id)},
        format="json",
    )
    assert rep4.status_code == status.HTTP_403_FORBIDDEN
    assert rep4.json()["erreur"]["code"] == "action_reservee_dg"


@pytest.mark.django_db
def test_rec_s1_10_b_substitution_obligatoire(client_tenant, dg_user):
    """REC-S1-10-B : La suppression exige role_substitution_id (400 substitution_obligatoire)."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_custom = Role.objects.create(
            code="SPECIALISTE_FACADE",
            libelle="Spécialiste Façade",
            est_systeme=False,
            est_actif=True,
        )

    cl_dg = auth_client(client_tenant, dg_user)

    # Sans substitution
    rep = cl_dg.post(
        f"/api/v1/roles/{role_custom.id}/supprimer/",
        {},
        format="json",
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert rep.json()["erreur"]["code"] == "substitution_obligatoire"


@pytest.mark.django_db
def test_rec_s1_10_c_suppression_et_reaffectation_atomique(client_tenant, dg_user):
    """REC-S1-10-C : Réassignation atomique vers le rôle de substitution."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_ct = Role.objects.get(code=RoleGlobal.CONDUCTEUR_TRAVAUX)

        # Rôle personnalisé à supprimer
        role_adjoint = Role.objects.create(
            code="CONDUCTEUR_ADJOINT",
            libelle="Conducteur de travaux adjoint",
            est_systeme=False,
            est_actif=True,
        )

        # Utilisateur lié à ce rôle personnalisé
        collaborateur = Utilisateur.objects.create_user(
            email="adjoint@demo.ci",
            password=MOT_DE_PASSE,
            nom="Koné",
            prenom="Fousseni",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            role_personnalise=role_adjoint,
            statut=StatutUtilisateur.ACTIF,
        )

        # Projet et affectation liés à ce rôle
        tiers = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="Client Test",
            telephone="+22501010101",
        )
        projet = Projet.objects.create(
            reference="PRJ-2026-TEST",
            nom="Chantier Réaffectation",
            client=tiers,
            chef_projet=dg_user,
            date_debut_prevue="2026-09-01",
            date_fin_prevue="2026-12-31",
            ville="Abidjan",
        )
        affectation = AffectationProjet.objects.create(
            projet=projet,
            utilisateur=collaborateur,
            role=role_adjoint,
            role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
            est_actif=True,
        )

    cl_dg = auth_client(client_tenant, dg_user)

    rep = cl_dg.post(
        f"/api/v1/roles/{role_adjoint.id}/supprimer/",
        {"role_substitution_id": str(role_ct.id)},
        format="json",
    )

    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert data["role_supprime"] == "CONDUCTEUR_ADJOINT"
    assert data["utilisateurs_reassignes"] == 1
    assert data["affectations_reassignees"] == 1

    # Vérifications en base de données
    with schema_context(SCHEMA):
        collaborateur.refresh_from_db()
        assert collaborateur.role_personnalise == role_ct

        affectation.refresh_from_db()
        assert affectation.role == role_ct

        role_adjoint.refresh_from_db()
        assert role_adjoint.supprime_le is not None
        assert role_adjoint.est_actif is False
