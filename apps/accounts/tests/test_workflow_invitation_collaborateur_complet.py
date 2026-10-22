"""Tests d'intégration du cycle de vie unifié des invitations et collaborateurs.

Couvre :
1. Ajout d'un collaborateur via /api/v1/invitations/ avec statut INVITE immédiat.
2. Affectation à un chantier refusée tant que le compte n'est pas activé, acceptée ensuite.
3. Retrait local d'un collaborateur d'un chantier précis (PATCH est_actif=False et DELETE).
4. Retrait global d'un collaborateur de toute la plateforme (DELETE /api/v1/invitations/{id}/).
   - Vérification de la clôture automatique de toutes les affectations actives.
   - Révocation des invitations en attente.
   - Désactivation du compte (statut DESACTIVE, is_active=False).
5. Inviolabilité du compte du Directeur Général / Propriétaire (rejet 403 sur DELETE).
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutProjet,
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
    """Directeur Général (DG) / Propriétaire."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.unifie@demo.ci",
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
        user.password = make_password(MOT_DE_PASSE)
        user.save()
        return user


@pytest.fixture
def admin_user(db):
    """Administrateur délégué."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.unifie@demo.ci",
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
        user.password = make_password(MOT_DE_PASSE)
        user.save()
        return user


@pytest.fixture
def chantier_test(db, dg_user):
    """Chantier de démonstration pour les tests d'affectation."""
    with schema_context(SCHEMA):
        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="Client Immobilier SA",
            defaults={"type_tiers": TypeTiers.ENTREPRISE, "ville": "Abidjan"},
        )
        projet, _ = Projet.objects.get_or_create(
            reference="PRJ-UNIFIE-001",
            defaults={
                "nom": "Chantier Tour Panoramique",
                "client": client_tiers,
                "chef_projet": dg_user,
                "ville": "Abidjan",
                "date_debut_prevue": date.today(),
                "date_fin_prevue": date.today() + timedelta(days=90),
                "statut": StatutProjet.EN_COURS,
                "cree_par": dg_user,
            },
        )
        return projet


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_workflow_invitation_et_affectation_apres_activation(
    client_tenant, admin_user, chantier_test
):
    """Un collaborateur invité ne peut être affecté à un chantier qu'une fois son compte activé."""
    client = _auth(client_tenant, admin_user)

    # 1. Émission de l'invitation via la route unifiée /api/v1/invitations/
    payload_invit = {
        "email": "moussa.diallo@demo.ci",
        "nom": "DIALLO",
        "prenom": "Moussa",
        "telephone": "+2250701020304",
        "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
    }
    rep_invit = client.post("/api/v1/invitations/", payload_invit, format="json")
    assert rep_invit.status_code == status.HTTP_201_CREATED
    data_invit = rep_invit.json()

    collab_id = data_invit["id"]
    assert data_invit["statut"] == "INVITE"
    assert data_invit["email"] == "moussa.diallo@demo.ci"
    assert data_invit["role_global"] == RoleGlobal.CONDUCTEUR_TRAVAUX
    assert data_invit["lien_activation"] is not None
    assert "jeton=" in data_invit["lien_activation"]

    # Vérification que le collaborateur existe déjà en base comme Utilisateur INVITE
    with schema_context(SCHEMA):
        u = Utilisateur.objects.get(id=collab_id)
        assert u.statut == StatutUtilisateur.INVITE
        assert u.has_usable_password() is False

    # 2. L'affectation à un chantier exige un compte actif : tant que l'invité n'a pas activé
    # son compte, elle est refusée (400 candidat_invalide)
    payload_aff = {
        "utilisateur_id": str(collab_id),
        "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
        "date_debut": str(date.today()),
        "date_fin": str(date.today() + timedelta(days=60)),
    }
    url_aff = f"/api/v1/projets/{chantier_test.id}/affectations/"
    rep_refus = client.post(url_aff, payload_aff, format="json")
    assert rep_refus.status_code == status.HTTP_400_BAD_REQUEST
    assert rep_refus.json()["erreur"]["details"]["code"] == ["candidat_invalide"]

    # 3. L'invité figure dans la liste globale /api/v1/invitations/, sans chantier
    rep_liste = client.get("/api/v1/invitations/")
    assert rep_liste.status_code == status.HTTP_200_OK
    collab_entry = next((c for c in rep_liste.json() if c["id"] == str(collab_id)), None)
    assert collab_entry is not None
    assert collab_entry["statut"] == "INVITE"
    assert collab_entry["projets"] == []

    # 4. Une fois le compte activé, l'affectation est acceptée et apparaît dans la liste
    with schema_context(SCHEMA):
        Utilisateur.objects.filter(id=collab_id).update(statut=StatutUtilisateur.ACTIF)
    rep_aff = client.post(url_aff, payload_aff, format="json")
    assert rep_aff.status_code == status.HTTP_201_CREATED, rep_aff.json()
    data_aff = rep_aff.json()
    assert data_aff["est_actif"] is True
    assert data_aff["role_projet"] == RoleProjet.CONDUCTEUR_TRAVAUX
    assert data_aff["utilisateur"]["statut"] == "ACTIF"

    rep_liste = client.get("/api/v1/invitations/")
    collab_entry = next((c for c in rep_liste.json() if c["id"] == str(collab_id)), None)
    assert collab_entry["statut"] == "ACTIF"
    assert collab_entry["projets"][0]["reference"] == "PRJ-UNIFIE-001"


@pytest.mark.django_db
def test_retrait_local_collaborateur_du_chantier(client_tenant, admin_user, chantier_test):
    """Vérifie le retrait d'un collaborateur d'un chantier précis sans le chasser de l'entreprise."""
    client = _auth(client_tenant, admin_user)

    # Création collaborateur
    with schema_context(SCHEMA):
        collab = Utilisateur.objects.create(
            email="terrain.retrait@demo.ci",
            nom="Konan",
            prenom="Jean",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )
        aff = AffectationProjet.objects.create(
            projet=chantier_test,
            utilisateur=collab,
            role_projet=RoleProjet.CHEF_CHANTIER,
            est_actif=True,
        )

    url_aff = f"/api/v1/projets/{chantier_test.id}/affectations/{aff.id}/"

    # Option A : Désactivation logique (PATCH est_actif=False)
    rep_patch = client.patch(url_aff, {"est_actif": False}, format="json")
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.json()["est_actif"] is False

    # Le collaborateur existe toujours dans l'entreprise
    with schema_context(SCHEMA):
        collab.refresh_from_db()
        assert collab.statut == StatutUtilisateur.ACTIF

    # Option B : Suppression définitive de l'équipe (DELETE)
    rep_del = client.delete(f"{url_aff}?hard=true")
    assert rep_del.status_code == status.HTTP_204_NO_CONTENT

    with schema_context(SCHEMA):
        assert not AffectationProjet.objects.filter(id=aff.id).exists()
        # Le compte utilisateur de l'entreprise est intact
        assert Utilisateur.objects.filter(id=collab.id).exists()


@pytest.mark.django_db
def test_retrait_global_collaborateur_plateforme(client_tenant, admin_user, chantier_test):
    """Vérifie le retrait d'un collaborateur de toute la plateforme (départ de l'entreprise)."""
    client = _auth(client_tenant, admin_user)

    # 1. Création d'un collaborateur avec affectation active et invitation en attente
    with schema_context(SCHEMA):
        collab = Utilisateur.objects.create(
            email="depart.salarie@demo.ci",
            nom="Kouadio",
            prenom="Serge",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.INVITE,
        )
        aff = AffectationProjet.objects.create(
            projet=chantier_test,
            utilisateur=collab,
            role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
            est_actif=True,
        )
        inv = Invitation.objects.create(
            email=collab.email,
            nom="Serge Kouadio",
            role_propose=RoleGlobal.CONDUCTEUR_TRAVAUX,
            empreinte=Invitation.empreinte_de("jeton-depart-123"),
            expire_le=date.today() + timedelta(days=3),
            statut=Invitation.Statut.ENVOYEE,
        )

    # 2. Appel DELETE sur /api/v1/invitations/{id}/
    rep_del = client.delete(f"/api/v1/invitations/{collab.id}/")
    assert rep_del.status_code == status.HTTP_200_OK
    data = rep_del.json()
    assert data["statut"] == "DESACTIVE"
    assert "retiré de la plateforme" in data["message"].lower()

    # 3. Vérifications en base de données
    with schema_context(SCHEMA):
        collab.refresh_from_db()
        # Compte désactivé et soft-deleted
        assert collab.statut == StatutUtilisateur.DESACTIVE
        assert collab.is_active is False
        assert collab.supprime_le is not None
        assert collab.supprime_par == admin_user

        # Affectations clôturées automatiquement
        aff.refresh_from_db()
        assert aff.est_actif is False

        # Invitations révoquées
        inv.refresh_from_db()
        assert inv.statut == Invitation.Statut.REVOQUEE


@pytest.mark.django_db
def test_interdiction_retirer_dg_ou_proprietaire(client_tenant, admin_user, dg_user):
    """Rejette immédiatement avec HTTP 403 toute tentative de retrait du DG / Propriétaire."""
    client = _auth(client_tenant, admin_user)

    rep = client.delete(f"/api/v1/invitations/{dg_user.id}/")
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    assert rep.json()["erreur"]["code"] == "suppression_dg_interdite"
    assert "propriétaire ne peut pas être désactivé" in rep.json()["erreur"]["message"].lower()

    # Le DG lui-même ne peut pas non plus se retirer
    client = _auth(client_tenant, dg_user)
    rep_dg = client.delete(f"/api/v1/invitations/{dg_user.id}/")
    assert rep_dg.status_code == status.HTTP_403_FORBIDDEN
    assert rep_dg.json()["erreur"]["code"] == "suppression_dg_interdite"

    with schema_context(SCHEMA):
        dg_user.refresh_from_db()
        assert dg_user.statut == StatutUtilisateur.ACTIF
        assert dg_user.supprime_le is None
