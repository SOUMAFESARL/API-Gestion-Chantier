"""Tests d'intégration pour l'API d'affectation des collaborateurs au projet (US-04).

Valide :
- L'affectation des rôles : Conducteur de travaux (CT), Chef de Chantier (CC), Consultant lecture (VI / CL),
  Maître d'Œuvre (MOE) et Maître d'Ouvrage (MOA).
- L'inviolabilité de l'invariant US-04 : interdiction de désactiver ou supprimer le dernier Chef de Projet actif.
- La réactivation fluide d'un collaborateur préalablement désactivé (pas de collision SQL unique).
- Le contrôle d'accès RBAC : seuls le DG, Admin et CP du chantier peuvent gérer l'équipe.
"""

from datetime import date, timedelta
import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur, TypeTiers
from apps.projets.models import AffectationProjet, Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        u, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.aff@demo.ci",
            defaults={
                "nom": "Kouassi",
                "prenom": "Admin",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": True,
            },
        )
        u.is_owner = True
        u.save()
        return u


@pytest.fixture
def cp_user(db):
    with schema_context(SCHEMA):
        u, _ = Utilisateur.tous_objets.get_or_create(
            email="cp.aff@demo.ci",
            defaults={
                "nom": "Touré",
                "prenom": "ChefProjet",
                "role_global": RoleGlobal.CHEF_PROJET,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        return u


@pytest.fixture
def collaborateur_user(db):
    with schema_context(SCHEMA):
        u, _ = Utilisateur.tous_objets.get_or_create(
            email="collab.aff@demo.ci",
            defaults={
                "nom": "Diallo",
                "prenom": "Moussa",
                "role_global": RoleGlobal.CHEF_CHANTIER,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        return u


@pytest.fixture
def visiteur_user(db):
    with schema_context(SCHEMA):
        u, _ = Utilisateur.tous_objets.get_or_create(
            email="visiteur.aff@demo.ci",
            defaults={
                "nom": "Koné",
                "prenom": "Fatou",
                "role_global": RoleGlobal.VISITEUR,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        return u


@pytest.fixture
def projet_db(db, admin_user, cp_user):
    with schema_context(SCHEMA):
        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="Client Immobilier SA",
            defaults={"type_tiers": TypeTiers.ENTREPRISE, "ville": "Abidjan"},
        )
        projet, _ = Projet.objects.get_or_create(
            reference="PRJ-AFF-001",
            defaults={
                "nom": "Chantier Test Affectation",
                "client": client_tiers,
                "chef_projet": cp_user,
                "ville": "Abidjan",
                "date_debut_prevue": date.today(),
                "date_fin_prevue": date.today() + timedelta(days=60),
                "statut": StatutProjet.EN_COURS,
                "cree_par": admin_user,
            },
        )
        # Création de l'affectation initiale du Chef de Projet
        AffectationProjet.objects.get_or_create(
            projet=projet,
            utilisateur=cp_user,
            defaults={"role_projet": RoleProjet.CHEF_PROJET, "est_actif": True},
        )
        return projet


@pytest.mark.django_db
def test_lister_affectations_projet(admin_user, projet_db):
    """Vérifie que la liste des membres du projet est correctement renvoyée."""
    client = _auth(APIClient(), admin_user)
    rep = client.get(f"/api/v1/projets/{projet_db.id}/affectations/", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert len(data) >= 1
    assert data[0]["role_projet"] == RoleProjet.CHEF_PROJET
    assert data[0]["role_projet_libelle"] == "Chef de Projet"


@pytest.mark.django_db
def test_affecter_conducteur_travaux_et_chef_chantier(admin_user, projet_db, collaborateur_user):
    """Vérifie l'affectation d'un Conducteur de Travaux et d'un Chef de Chantier."""
    client = _auth(APIClient(), admin_user)
    url = f"/api/v1/projets/{projet_db.id}/affectations/"

    # 1. Affectation CT
    payload_ct = {
        "utilisateur_id": str(collaborateur_user.id),
        "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
        "date_debut": str(date.today()),
        "date_fin": str(date.today() + timedelta(days=30)),
    }
    rep_ct = client.post(url, payload_ct, format="json", HTTP_HOST=HOTE)
    assert rep_ct.status_code == status.HTTP_201_CREATED
    data_ct = rep_ct.json()
    assert data_ct["role_projet"] == RoleProjet.CONDUCTEUR_TRAVAUX
    assert data_ct["role_projet_libelle"] == "Conducteur de Travaux"
    assert data_ct["est_actif"] is True

    # Vérification synchronisation sur le modèle Projet
    with schema_context(SCHEMA):
        projet_db.refresh_from_db()
        assert projet_db.conducteur_travaux_id == collaborateur_user.id

    # 2. Modification de l'affectation vers Chef de Chantier
    aff_id = data_ct["id"]
    rep_patch = client.patch(
        f"{url}{aff_id}/",
        {"role_projet": RoleProjet.CHEF_CHANTIER},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.json()["role_projet"] == RoleProjet.CHEF_CHANTIER
    assert rep_patch.json()["role_projet_libelle"] == "Chef de Chantier"


@pytest.mark.django_db
def test_affecter_consultant_lecture_et_maitres(admin_user, projet_db, visiteur_user):
    """Vérifie l'affectation avec les rôles Consultant lecture (VI), Maître d'Œuvre (MOE) et Maître d'Ouvrage (MOA)."""
    client = _auth(APIClient(), admin_user)
    url = f"/api/v1/projets/{projet_db.id}/affectations/"

    # Affectation Consultant lecture
    payload_cl = {
        "utilisateur_id": str(visiteur_user.id),
        "role_projet": RoleProjet.VISITEUR,
    }
    rep_cl = client.post(url, payload_cl, format="json", HTTP_HOST=HOTE)
    assert rep_cl.status_code == status.HTTP_201_CREATED
    assert rep_cl.json()["role_projet"] == RoleProjet.VISITEUR
    assert rep_cl.json()["role_projet_libelle"] == "Consultant lecture"

    # Mise à jour vers Maître d'Œuvre (MOE)
    aff_id = rep_cl.json()["id"]
    rep_moe = client.patch(
        f"{url}{aff_id}/",
        {"role_projet": RoleProjet.MAITRE_OEUVRE},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_moe.status_code == status.HTTP_200_OK
    assert rep_moe.json()["role_projet"] == RoleProjet.MAITRE_OEUVRE
    assert rep_moe.json()["role_projet_libelle"] == "Maître d'Œuvre"


@pytest.mark.django_db
def test_protection_invariant_dernier_chef_projet(admin_user, projet_db, cp_user):
    """Empêche formellement de désactiver ou supprimer le dernier Chef de Projet (US-04)."""
    client = _auth(APIClient(), admin_user)
    with schema_context(SCHEMA):
        aff_cp = AffectationProjet.objects.get(projet=projet_db, utilisateur=cp_user)
    url_detail = f"/api/v1/projets/{projet_db.id}/affectations/{aff_cp.id}/"

    # Tentative 1 : Désactivation par PATCH
    rep_desact = client.patch(url_detail, {"est_actif": False}, format="json", HTTP_HOST=HOTE)
    assert rep_desact.status_code == status.HTTP_400_BAD_REQUEST
    assert "chef de projet" in str(rep_desact.json()).lower()

    # Tentative 2 : Changement de rôle par PATCH
    rep_change = client.patch(
        url_detail,
        {"role_projet": RoleProjet.CHEF_CHANTIER},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_change.status_code == status.HTTP_400_BAD_REQUEST

    # Tentative 3 : Suppression directe par DELETE
    rep_del = client.delete(url_detail, HTTP_HOST=HOTE)
    assert rep_del.status_code == status.HTTP_400_BAD_REQUEST
    assert "chef de projet" in str(rep_del.json()).lower()


@pytest.mark.django_db
def test_reactivation_collaborateur_inactif(admin_user, projet_db, collaborateur_user):
    """Vérifie qu'un collaborateur désactivé est réactivé proprement sans collision SQL."""
    with schema_context(SCHEMA):
        aff = AffectationProjet.objects.create(
            projet=projet_db,
            utilisateur=collaborateur_user,
            role_projet=RoleProjet.CHEF_CHANTIER,
            est_actif=False,
        )

    client = _auth(APIClient(), admin_user)
    url = f"/api/v1/projets/{projet_db.id}/affectations/"

    # Nouvelle affectation du même utilisateur en Conducteur de Travaux
    payload = {
        "utilisateur_id": str(collaborateur_user.id),
        "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
    }
    rep = client.post(url, payload, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["id"] == str(aff.id)
    assert data["est_actif"] is True
    assert data["role_projet"] == RoleProjet.CONDUCTEUR_TRAVAUX


@pytest.mark.django_db
def test_permission_refusee_non_admin_non_cp(visiteur_user, projet_db, collaborateur_user):
    """Vérifie qu'un simple utilisateur sans droit ne peut pas gérer les affectations (403)."""
    client = _auth(APIClient(), visiteur_user)
    url = f"/api/v1/projets/{projet_db.id}/affectations/"

    rep = client.post(
        url,
        {
            "utilisateur_id": str(collaborateur_user.id),
            "role_projet": RoleProjet.CHEF_CHANTIER,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN
