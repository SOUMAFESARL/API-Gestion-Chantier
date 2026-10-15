"""Tests pour la tâche B1 du lot 3 :
format standard des erreurs et journalisation des gestes sur collaborateurs et rôles.
"""

import pytest
from django.contrib.auth.hashers import make_password
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, StatutUtilisateur

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
            email="dg.erreurs@demo.ci",
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
    """Administrateur délégué (AD)."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.erreurs@demo.ci",
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
            email="ct.erreurs@demo.ci",
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
def test_suspendre_le_dg_dit_pourquoi(client_tenant, admin_user, dg_user):
    """L'AD tentant de suspendre le DG reçoit un 403 au format du produit."""
    _auth(client_tenant, admin_user)
    rep = client_tenant.post(f"/api/v1/parametres/collaborateurs/{dg_user.id}/suspendre/")
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    data = rep.json()
    assert "detail" not in data
    assert "erreur" in data
    assert "Directeur Général" in data["erreur"]["message"]


@pytest.mark.django_db
def test_suspendre_deux_fois_conflit_lisible(client_tenant, dg_user, collab_user):
    """Suspendre un compte déjà suspendu renvoie 409 Conflit au format standard."""
    _auth(client_tenant, dg_user)
    rep1 = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/suspendre/")
    assert rep1.status_code == status.HTTP_200_OK

    rep2 = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/suspendre/")
    assert rep2.status_code == status.HTTP_409_CONFLICT
    data = rep2.json()
    assert "detail" not in data
    assert "erreur" in data
    assert data["erreur"]["code"] == "conflit"
    assert "déjà suspendu" in data["erreur"]["message"]


@pytest.mark.django_db
def test_suspendre_son_propre_compte_400_lisible(client_tenant, admin_user):
    """Tenter de suspendre son propre compte est refusé de manière lisible."""
    _auth(client_tenant, admin_user)
    rep = client_tenant.post(f"/api/v1/parametres/collaborateurs/{admin_user.id}/suspendre/")
    # Selon la règle B-06, pour l'AD c'est 403 avec le message B-06
    assert rep.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)
    data = rep.json()
    assert "detail" not in data
    assert "erreur" in data
    assert "propre compte" in data["erreur"]["message"]


@pytest.mark.django_db
def test_reactiver_un_actif_conflit_lisible(client_tenant, dg_user, collab_user):
    """Réactiver un collaborateur déjà actif renvoie 409 conflit."""
    _auth(client_tenant, dg_user)
    rep = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/reactiver/")
    assert rep.status_code == status.HTTP_409_CONFLICT
    data = rep.json()
    assert "detail" not in data
    assert "erreur" in data
    assert data["erreur"]["code"] == "conflit"
    assert "déjà actif" in data["erreur"]["message"]


@pytest.mark.django_db
def test_role_portee_dg_403_lisible(client_tenant, admin_user, dg_user):
    """Modifier la portée d'un rôle par un non-DG renvoie 403 avec message lisible."""
    _auth(client_tenant, admin_user)
    with schema_context(SCHEMA):
        role_perso, _ = Role.objects.get_or_create(
            code="ROLE_TEST_PORTEE",
            defaults={
                "libelle": "Rôle Test Portée",
                "est_systeme": False,
                "portee": "PROJET",
            },
        )
        role_perso.est_systeme = False
        role_perso.save()
    rep = client_tenant.patch(
        f"/api/v1/parametres/roles/{role_perso.id}/",
        {"portee": "ENTREPRISE"},
        format="json",
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    data = rep.json()
    assert "detail" not in data
    assert "erreur" in data
    assert "portée" in data["erreur"]["message"]

    # Tentative sur le rôle DG par le DG lui-même -> 403 rôle immuable
    _auth(client_tenant, dg_user)
    with schema_context(SCHEMA):
        role_dg = Role.objects.get(code=RoleGlobal.DIRECTEUR_GENERAL)
    rep2 = client_tenant.patch(
        f"/api/v1/parametres/roles/{role_dg.id}/",
        {"portee": "PROJET"},
        format="json",
    )
    assert rep2.status_code == status.HTTP_403_FORBIDDEN
    data2 = rep2.json()
    assert "detail" not in data2
    assert "erreur" in data2


@pytest.mark.django_db
def test_suspension_journalisee(client_tenant, dg_user, collab_user):
    """La suspension d'un collaborateur est inscrite dans le JournalAudit."""
    _auth(client_tenant, dg_user)
    with schema_context(SCHEMA):
        JournalAudit.objects.filter(
            type_entite="utilisateur", entite_id=str(collab_user.id)
        ).delete()

    rep = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/suspendre/")
    assert rep.status_code == status.HTTP_200_OK

    with schema_context(SCHEMA):
        entree = JournalAudit.objects.filter(
            type_entite="utilisateur",
            entite_id=str(collab_user.id),
        ).latest("horodatage")
        assert entree.action == ActionAudit.MODIFICATION
        assert entree.utilisateur_id == dg_user.id
        assert entree.valeur_apres.get("geste") == "SUSPENSION"
        assert entree.valeur_apres.get("statut") == StatutUtilisateur.DESACTIVE


@pytest.mark.django_db
def test_reactivation_journalisee(client_tenant, dg_user, collab_user):
    """La réactivation d'un collaborateur est inscrite dans le JournalAudit."""
    _auth(client_tenant, dg_user)
    # Suspendre d'abord
    client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/suspendre/")

    with schema_context(SCHEMA):
        JournalAudit.objects.filter(
            type_entite="utilisateur", entite_id=str(collab_user.id)
        ).delete()

    rep = client_tenant.post(f"/api/v1/parametres/collaborateurs/{collab_user.id}/reactiver/")
    assert rep.status_code == status.HTTP_200_OK

    with schema_context(SCHEMA):
        entree = JournalAudit.objects.filter(
            type_entite="utilisateur",
            entite_id=str(collab_user.id),
        ).latest("horodatage")
        assert entree.action == ActionAudit.MODIFICATION
        assert entree.utilisateur_id == dg_user.id
        assert entree.valeur_apres.get("geste") == "REACTIVATION"
        assert entree.valeur_apres.get("statut") == StatutUtilisateur.ACTIF


@pytest.mark.django_db
def test_retrait_journalise(client_tenant, dg_user, collab_user):
    """Le retrait définitif d'un collaborateur (DELETE) est inscrit dans le JournalAudit."""
    _auth(client_tenant, dg_user)
    email_avant = collab_user.email
    with schema_context(SCHEMA):
        JournalAudit.objects.filter(
            type_entite="utilisateur", entite_id=str(collab_user.id)
        ).delete()

    rep = client_tenant.delete(f"/api/v1/parametres/collaborateurs/{collab_user.id}/")
    assert rep.status_code == status.HTTP_200_OK

    with schema_context(SCHEMA):
        entree = JournalAudit.objects.filter(
            type_entite="utilisateur",
            entite_id=str(collab_user.id),
        ).latest("horodatage")
        assert entree.action == ActionAudit.SUPPRESSION
        assert entree.valeur_avant.get("email") == email_avant
        assert entree.valeur_apres.get("geste") == "RETRAIT"


@pytest.mark.django_db
def test_refus_ne_journalise_pas(client_tenant, admin_user, dg_user):
    """Une action refusée (403) n'écrit pas dans le JournalAudit."""
    _auth(client_tenant, admin_user)
    with schema_context(SCHEMA):
        JournalAudit.objects.filter(
            type_entite="utilisateur", entite_id=str(dg_user.id)
        ).delete()

    rep = client_tenant.post(f"/api/v1/parametres/collaborateurs/{dg_user.id}/suspendre/")
    assert rep.status_code == status.HTTP_403_FORBIDDEN

    with schema_context(SCHEMA):
        entrees = JournalAudit.objects.filter(
            type_entite="utilisateur", entite_id=str(dg_user.id)
        )
        assert not entrees.exists()
