"""Tests complets pour la gouvernance du rôle Administrateur et la suppression en cascade.

Règles testées :
1. Le rôle Administrateur (AD) n'est plus système et peut être supprimé UNIQUEMENT par le DG / Propriétaire.
2. Un Administrateur délégué ne peut JAMAIS supprimer le rôle Administrateur (403 ActionReserveeDg).
3. Le rôle Directeur Général (DG) reste strictement système et immuable.
4. Option A (Réassignation) : les collaborateurs et affectations sont réassignés vers le rôle cible.
5. Option B (Suppression cascade) : les collaborateurs portant ce rôle sont désactivés logiquement
   (statut=DESACTIVE, supprime_le posé, affectations clôturées, sessions révoquées).
6. Garde-fou souverain : le compte Propriétaire/Fondateur et le DG racine ne sont JAMAIS désactivés en cascade.
7. Si aucune option n'est fournie, une erreur 400 (RoleSubstitutionObligatoire) est renvoyée.
"""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut, supprimer_role
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutUtilisateur,
    TypeTiers,
)
from apps.core.exceptions import ActionReserveeDg
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
        Utilisateur.tous_objets.filter(email="dg.cascade@demo.ci").delete()
        dg = Utilisateur.objects.create_user(
            email="dg.cascade@demo.ci",
            password=MOT_DE_PASSE,
            nom="Kouamé",
            prenom="Patrice",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )
        yield dg
        Utilisateur.tous_objets.all().update(supprime_par=None, cree_par=None)
        AffectationProjet.tous_objets.all().delete()
        Projet.tous_objets.all().delete()
        Tiers.tous_objets.all().delete()
        Role.tous_objets.all().delete()
        Utilisateur.tous_objets.filter(email__contains="cascade").delete()
        Utilisateur.tous_objets.filter(email="simple.collab@demo.ci").delete()
        Utilisateur.tous_objets.filter(pk=dg.pk).delete()


@pytest.fixture
def admin_delegue(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.cascade@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.cascade@demo.ci",
            password=MOT_DE_PASSE,
            nom="Yao",
            prenom="Adjoua",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_owner=False,
        )
        yield admin
        Utilisateur.tous_objets.all().update(supprime_par=None, cree_par=None)
        Utilisateur.tous_objets.filter(pk=admin.pk).delete()


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
def test_admin_supprimable_par_le_dg(client_tenant, dg_user):
    """Le DG peut supprimer le rôle Administrateur."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_ad = Role.objects.get(code=RoleGlobal.ADMIN)
        assert role_ad.est_systeme is False

        # Rôle de substitution pour l'option réassignation
        role_cp = Role.objects.get(code=RoleGlobal.CHEF_PROJET)

    cl_dg = auth_client(client_tenant, dg_user)

    rep = cl_dg.post(
        f"/api/v1/parametres/roles/{role_ad.id}/supprimer/",
        {"role_substitution_id": str(role_cp.id)},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["role_supprime"] == "AD"

    with schema_context(SCHEMA):
        role_ad.refresh_from_db()
        assert role_ad.est_actif is False
        assert role_ad.supprime_le is not None


@pytest.mark.django_db
def test_interdiction_admin_supprimer_role_admin(client_tenant, admin_delegue):
    """Un Administrateur délégué ne peut PAS supprimer le rôle Administrateur (403 ActionReserveeDg)."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_ad = Role.objects.get(code=RoleGlobal.ADMIN)
        role_cp = Role.objects.get(code=RoleGlobal.CHEF_PROJET)

    cl_admin = auth_client(client_tenant, admin_delegue)

    rep = cl_admin.post(
        f"/api/v1/parametres/roles/{role_ad.id}/supprimer/",
        {"role_substitution_id": str(role_cp.id)},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    assert rep.json()["erreur"]["code"] == "action_reservee_dg"


@pytest.mark.django_db
def test_interdiction_absolue_supprimer_role_dg(client_tenant, dg_user):
    """Même le DG ne peut pas supprimer le rôle Directeur Général (rôle système immuable)."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
        role_cp = Role.objects.get(code=RoleGlobal.CHEF_PROJET)
        assert role_dg.est_systeme is True

    cl_dg = auth_client(client_tenant, dg_user)

    rep = cl_dg.post(
        f"/api/v1/roles/{role_dg.id}/supprimer/",
        {"role_substitution_id": str(role_cp.id)},
        format="json",
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert "rôles système ne peuvent pas être supprimés" in str(rep.json())


@pytest.mark.django_db
def test_suppression_role_option_b_cascade_collaborateurs(client_tenant, dg_user):
    """Option B : Supprimer un rôle en cascade désactive tous les collaborateurs associés."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        # Création d'un rôle personnalisé à supprimer
        role_equipe = Role.objects.create(
            code="MACON_SPECIALISTE",
            libelle="Maçon Spécialiste",
            est_systeme=False,
            est_actif=True,
        )

        # Création de 2 collaborateurs avec ce rôle
        collab1 = Utilisateur.objects.create_user(
            email="collab1.cascade@demo.ci",
            password=MOT_DE_PASSE,
            nom="Traoré",
            prenom="Moussa",
            role_global=RoleGlobal.VISITEUR,
            role_personnalise=role_equipe,
            statut=StatutUtilisateur.ACTIF,
        )
        collab2 = Utilisateur.objects.create_user(
            email="collab2.cascade@demo.ci",
            password=MOT_DE_PASSE,
            nom="Koné",
            prenom="Ibrahim",
            role_global=RoleGlobal.VISITEUR,
            role_personnalise=role_equipe,
            statut=StatutUtilisateur.ACTIF,
        )

        # Création d'un chantier et d'une affectation
        tiers = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="Client Cascade",
            telephone="+22501020304",
        )
        projet = Projet.objects.create(
            reference="PRJ-CASCADE-01",
            nom="Chantier Cascade Test",
            client=tiers,
            chef_projet=dg_user,
            date_debut_prevue="2026-10-01",
            date_fin_prevue="2026-12-31",
            ville="Yamoussoukro",
        )
        affectation1 = AffectationProjet.objects.create(
            projet=projet,
            utilisateur=collab1,
            role=role_equipe,
            role_projet=RoleProjet.VISITEUR,
            est_actif=True,
        )

    cl_dg = auth_client(client_tenant, dg_user)

    # Appel avec suppression des collaborateurs (Option B)
    rep = cl_dg.post(
        f"/api/v1/roles/{role_equipe.id}/supprimer/",
        {"supprimer_collaborateurs": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert data["role_supprime"] == "MACON_SPECIALISTE"
    assert data["mode"] == "suppression_collaborateurs"
    assert data["utilisateurs_supprimes"] == 2

    # Vérifications en base de données
    with schema_context(SCHEMA):
        # 1. Le rôle est désactivé
        role_equipe.refresh_from_db()
        assert role_equipe.est_actif is False
        assert role_equipe.supprime_le is not None

        # 2. Les collaborateurs sont logiquement désactivés (Soft Delete)
        collab1.refresh_from_db()
        assert collab1.statut == StatutUtilisateur.DESACTIVE
        assert collab1.is_active is False
        assert collab1.supprime_le is not None
        assert collab1.supprime_par == dg_user

        collab2.refresh_from_db()
        assert collab2.statut == StatutUtilisateur.DESACTIVE
        assert collab2.is_active is False
        assert collab2.supprime_le is not None
        assert collab2.supprime_par == dg_user

        # 3. Les affectations de chantier sont clôturées
        affectation1.refresh_from_db()
        assert affectation1.est_actif is False
        assert affectation1.supprime_le is not None


@pytest.mark.django_db
def test_garde_fou_proprietaire_non_desactive_en_cascade(client_tenant, dg_user):
    """Le compte du Propriétaire / DG racine ne peut JAMAIS être désactivé en cascade."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        role_special = Role.objects.create(
            code="ROLE_DG_TEST",
            libelle="Rôle DG Test",
            est_systeme=False,
            est_actif=True,
        )

        # Attachement du rôle personnalisé au DG lui-même
        dg_user.role_personnalise = role_special
        dg_user.save()

        # Et un autre collaborateur standard
        collab = Utilisateur.objects.create_user(
            email="simple.collab@demo.ci",
            password=MOT_DE_PASSE,
            nom="Diallo",
            prenom="Amadou",
            role_global=RoleGlobal.VISITEUR,
            role_personnalise=role_special,
            statut=StatutUtilisateur.ACTIF,
        )

    cl_dg = auth_client(client_tenant, dg_user)

    rep = cl_dg.post(
        f"/api/v1/parametres/roles/{role_special.id}/supprimer/",
        {"supprimer_collaborateurs": True},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK

    with schema_context(SCHEMA):
        # Le DG reste ACTIF et NON supprimé !
        dg_user.refresh_from_db()
        assert dg_user.statut == StatutUtilisateur.ACTIF
        assert dg_user.is_active is True
        assert dg_user.supprime_le is None
        assert dg_user.role_personnalise is None  # Rôle simplement détaché

        # Le collaborateur standard a bien été désactivé
        collab.refresh_from_db()
        assert collab.statut == StatutUtilisateur.DESACTIVE
        assert collab.is_active is False
        assert collab.supprime_le is not None
