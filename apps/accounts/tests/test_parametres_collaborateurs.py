"""Tests pour l'API des collaborateurs dans les paramètres (/api/v1/parametres/collaborateurs/)."""

from datetime import timedelta
import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Role, Utilisateur
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


from django.contrib.auth.hashers import make_password

@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def dg_user(db):
    """Directeur Général (DG), is_owner=True."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.param.collab@demo.ci",
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
    """Administrateur délégué (AD), is_owner=False."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="ad.param.collab@demo.ci",
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
def collaborateur_user(db):
    """Collaborateur standard (Conducteur de travaux)."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="ct.param.collab@demo.ci",
            defaults={
                "nom": "Kouassi",
                "prenom": "Yves",
                "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.CONDUCTEUR_TRAVAUX
        user.is_owner = False
        user.password = make_password(MOT_DE_PASSE)
        user.save()
        return user


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_get_parametres_collaborateurs_liste_avec_projets(
    client_tenant, collaborateur_user, dg_user
):
    """GET /api/v1/parametres/collaborateurs/ renvoie les collaborateurs et leurs projets associés."""
    with schema_context(SCHEMA):
        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="Client Test",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+2250102030405",
            },
        )

        # 1. Projet où le collaborateur est chef_projet direct
        p1, _ = Projet.objects.get_or_create(
            reference="PRJ-TEST-CP-01",
            defaults={
                "nom": "Chantier Tour A",
                "client": client_tiers,
                "ville": "Abidjan",
                "date_debut_prevue": timezone.now().date(),
                "date_fin_prevue": (timezone.now() + timedelta(days=60)).date(),
                "chef_projet": collaborateur_user,
                "statut": StatutProjet.EN_COURS,
            },
        )

        # 2. Projet où le collaborateur est affecté via AffectationProjet
        p2, _ = Projet.objects.get_or_create(
            reference="PRJ-TEST-AFF-02",
            defaults={
                "nom": "Chantier Résidence B",
                "client": client_tiers,
                "ville": "Bouaké",
                "date_debut_prevue": timezone.now().date(),
                "date_fin_prevue": (timezone.now() + timedelta(days=90)).date(),
                "chef_projet": dg_user,
                "statut": StatutProjet.EN_COURS,
            },
        )
        AffectationProjet.objects.get_or_create(
            utilisateur=collaborateur_user,
            projet=p2,
            defaults={
                "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
                "est_actif": True,
            },
        )

        # 3. Invitation en attente sans compte Utilisateur
        Invitation.objects.create(
            email="invite.seul@demo.ci",
            nom="Invite Seul",
            role_propose=RoleGlobal.CHEF_CHANTIER,
            empreinte=Invitation.empreinte_de("jeton-test-123"),
            expire_le=timezone.now() + timedelta(days=3),
            statut=Invitation.Statut.ENVOYEE,
        )

    client = _auth(client_tenant, collaborateur_user)
    rep = client.get("/api/v1/parametres/collaborateurs/")
    assert rep.status_code == status.HTTP_200_OK

    data = rep.json()
    assert isinstance(data, list)
    assert len(data) >= 3

    # Trouver le collaborateur test
    collab_entry = next((c for c in data if c["id"] == str(collaborateur_user.id)), None)
    assert collab_entry is not None
    assert collab_entry["email"] == "ct.param.collab@demo.ci"
    assert collab_entry["nom_complet"] == "Yves Kouassi"
    assert collab_entry["statut"] == "ACTIF"

    projets_collab = collab_entry["projets"]
    assert len(projets_collab) >= 2
    refs = [p["reference"] for p in projets_collab]
    assert "PRJ-TEST-CP-01" in refs
    assert "PRJ-TEST-AFF-02" in refs

    # Vérifier l'invité sans compte Utilisateur
    invite_entry = next((c for c in data if c["email"] == "invite.seul@demo.ci"), None)
    assert invite_entry is not None
    assert invite_entry["statut"] == "INVITE"
    assert invite_entry["projets"] == []


@pytest.mark.django_db
def test_post_parametres_collaborateurs_par_admin(client_tenant, admin_user):
    """Un administrateur peut inviter un conducteur de travaux via POST."""
    client = _auth(client_tenant, admin_user)
    payload = {
        "email": "nouveau.conducteur@demo.ci",
        "nom": "Gbagbo",
        "prenom": "Laurent",
        "telephone": "+2250700112233",
        "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
    }
    rep = client.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED

    data = rep.json()
    assert data["email"] == "nouveau.conducteur@demo.ci"
    assert data["nom"] == "Gbagbo"
    assert data["prenom"] == "Laurent"
    assert data["statut"] == "INVITE"
    assert data["role_global"] == RoleGlobal.CONDUCTEUR_TRAVAUX
    assert data["lien_activation"] is not None
    assert "jeton=" in data["lien_activation"]

    with schema_context(SCHEMA):
        u = Utilisateur.objects.get(email="nouveau.conducteur@demo.ci")
        assert u.statut == StatutUtilisateur.INVITE
        assert u.has_usable_password() is False


@pytest.mark.django_db
def test_post_parametres_collaborateurs_dg_peut_inviter_admin(client_tenant, dg_user):
    """Le DG peut inviter un nouvel administrateur."""
    client = _auth(client_tenant, dg_user)
    payload = {
        "email": "nouvel.admin@demo.ci",
        "nom": "Soro",
        "prenom": "Guillaume",
        "role_global": RoleGlobal.ADMIN,
    }
    rep = client.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    assert rep.json()["role_global"] == RoleGlobal.ADMIN


@pytest.mark.django_db
def test_post_parametres_collaborateurs_admin_ne_peut_pas_inviter_admin(client_tenant, admin_user):
    """Un administrateur délégué (non DG/Owner) ne peut pas inviter un autre ADMIN (R-DEMO-01)."""
    client = _auth(client_tenant, admin_user)
    payload = {
        "email": "tentative.admin@demo.ci",
        "nom": "Koné",
        "role_global": RoleGlobal.ADMIN,
    }
    rep = client.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_post_parametres_collaborateurs_interdit_role_dg(client_tenant, dg_user):
    """Le rôle DIRECTEUR_GENERAL ne peut pas être attribué (règle d'immutabilité)."""
    client = _auth(client_tenant, dg_user)
    payload = {
        "email": "imposteur.dg@demo.ci",
        "nom": "Usurpateur",
        "role_global": RoleGlobal.DIRECTEUR_GENERAL,
    }
    rep = client.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert rep.json()["erreur"]["code"] == "role_dg_non_attribuable"


@pytest.mark.django_db
def test_post_parametres_collaborateurs_refuse_si_email_deja_actif(
    client_tenant, admin_user, collaborateur_user
):
    """Rejette avec 400 si l'email correspond à un collaborateur déjà actif."""
    client = _auth(client_tenant, admin_user)
    payload = {
        "email": collaborateur_user.email,
        "nom": "Doublon",
        "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
    }
    rep = client.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert rep.json()["erreur"]["code"] == "email_deja_utilise"


@pytest.mark.django_db
def test_post_parametres_collaborateurs_refuse_aux_non_admins(client_tenant, collaborateur_user):
    """Un collaborateur non admin/DG reçoit 403 Forbidden sur la création."""
    client = _auth(client_tenant, collaborateur_user)
    payload = {
        "email": "infiltre@demo.ci",
        "nom": "Infiltré",
        "role_global": RoleGlobal.CHEF_CHANTIER,
    }
    rep = client.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN
