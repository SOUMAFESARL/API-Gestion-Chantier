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
        # Pas de nettoyage après le yield : la transaction du test est annulée, et supprimer les
        # rôles échoue dès qu'un utilisateur les référence (FK protégée `Utilisateur.role`).
        yield dg


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
    """REC-S1-10-A : La gestion des rôles est fermée à qui n'a pas `administration.roles_gerer`,
    et plusieurs gestes restent réservés au DG (403 pour les autres).

    Règle actuelle : l'AD détient `roles_gerer` (7 droits fixes) — il crée des rôles dans la
    limite de ses propres droits, mais ne modifie pas les rôles système et ne supprime pas
    le rôle AD.
    """
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_vi = Role.objects.get(code=RoleGlobal.VISITEUR)
        role_ad = Role.objects.get(code=RoleGlobal.ADMIN)

    # 1. Un conducteur de travaux (sans `roles_gerer`) tente de créer un rôle
    cl_ct = auth_client(client_tenant, conducteur_user)
    rep1 = cl_ct.post(
        "/api/v1/roles/",
        {"code": "TEST_CT", "libelle": "Test CT", "permissions_modules": {}},
        format="json",
    )
    assert rep1.status_code == status.HTTP_403_FORBIDDEN
    assert rep1.json()["erreur"]["code"] == "action_reservee_dg"

    # 2. Un administrateur délégué crée un rôle dans la limite de ses droits, pas au-delà
    cl_ad = auth_client(client_tenant, admin_delegue_user)
    rep2 = cl_ad.post(
        "/api/v1/roles/",
        {"code": "TEST_AD", "libelle": "Test AD", "permissions_modules": {}},
        format="json",
    )
    assert rep2.status_code == status.HTTP_201_CREATED
    rep2b = cl_ad.post(
        "/api/v1/roles/",
        {
            "code": "TEST_AD_MONTANTS",
            "libelle": "Test AD montants",
            "permissions_modules": {"projets": ["projets.lire", "projets.voir_montants"]},
        },
        format="json",
    )
    assert rep2b.status_code == status.HTTP_403_FORBIDDEN
    assert rep2b.json()["erreur"]["code"] == "action_reservee_dg"

    # 3. L'administrateur délégué tente de modifier un rôle système
    rep3 = cl_ad.patch(
        f"/api/v1/roles/{role_vi.id}/",
        {"libelle": "Visiteur Modifié"},
        format="json",
    )
    assert rep3.status_code == status.HTTP_403_FORBIDDEN
    assert rep3.json()["erreur"]["code"] == "modification_role_systeme_interdite"

    # 4. L'administrateur délégué tente de supprimer le rôle AD : réservé au DG
    rep4 = cl_ad.post(
        f"/api/v1/roles/{role_ad.id}/supprimer/",
        {"role_substitution_id": str(role_vi.id)},
        format="json",
    )
    assert rep4.status_code == status.HTTP_403_FORBIDDEN
    assert rep4.json()["erreur"]["code"] == "action_reservee_dg"

    # 5. Et un rôle système n'est supprimable par personne (le DG y compris)
    rep5 = cl_ad.post(
        f"/api/v1/roles/{role_vi.id}/supprimer/",
        {"role_substitution_id": str(role_ad.id)},
        format="json",
    )
    assert rep5.status_code == status.HTTP_400_BAD_REQUEST
    assert "rôles système ne peuvent pas être supprimés" in rep5.json()["erreur"]["message"]


@pytest.mark.django_db
def test_rec_s1_10_b_substitution_obligatoire(client_tenant, dg_user):
    """REC-S1-10-B : Supprimer un rôle porté par un collaborateur exige role_substitution_id
    (400 substitution_obligatoire) ; un rôle sans porteur se supprime directement.
    """
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_custom = Role.objects.create(
            code="SPECIALISTE_FACADE",
            libelle="Spécialiste Façade",
            est_systeme=False,
            est_actif=True,
        )
        role_vide = Role.objects.create(
            code="ROLE_SANS_PORTEUR",
            libelle="Rôle sans porteur",
            est_systeme=False,
            est_actif=True,
        )
        Utilisateur.objects.create_user(
            email="facade@demo.ci",
            password=MOT_DE_PASSE,
            nom="Traoré",
            prenom="Issa",
            role=role_custom,
            statut=StatutUtilisateur.ACTIF,
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

    # Rôle sans porteur : aucune substitution nécessaire
    rep_vide = cl_dg.post(
        f"/api/v1/roles/{role_vide.id}/supprimer/",
        {},
        format="json",
    )
    assert rep_vide.status_code == status.HTTP_200_OK


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
    assert data["affectations_reassignees"] == 0

    # Vérifications en base de données
    with schema_context(SCHEMA):
        collaborateur.refresh_from_db()
        # `role_personnalise` ne désigne plus que les rôles non système : le CT en est un
        assert collaborateur.role == role_ct

        affectation.refresh_from_db()
        assert affectation.est_actif is True

        role_adjoint.refresh_from_db()
        assert role_adjoint.supprime_le is not None
        assert role_adjoint.est_actif is False
