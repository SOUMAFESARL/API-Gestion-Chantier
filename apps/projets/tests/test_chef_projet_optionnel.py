"""Tests complets pour la fonctionnalité : Chef de Projet Optionnel sur un Chantier (Sprint 3 Tâche 08).

Couvre :
1. Création sans CP par le DG / Admin (201 CREATED, chef_projet=null, 0 affectation CP).
2. Création avec seulement un Conducteur de Travaux sans CP (aucun hack de substitution).
3. Interdiction de création pour les non-DG / non-Admin (403 FORBIDDEN).
4. Détachement d'un CP existant via PATCH chef_projet_id: null (200 OK, désactivation affectation).
5. Attribution d'un CP sur un chantier sans CP via PATCH (200 OK, création affectation).
6. Gouvernance de l'équipe par la Direction seule sur un chantier sans CP (403 pour tiers, 201 pour DG/Admin).
7. Non-régression du Tableau de Bord (pas d'AttributeError sur chef_projet=None).
8. Évolution de statut autorisée pour un chantier sans CP (EN_ATTENTE -> EN_COURS -> TERMINE).
"""

from datetime import date, timedelta
import pytest
from django.contrib.auth.hashers import make_password
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur, TypeTiers
from apps.projets.models import AffectationProjet, Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "PassTestCP123!"

pytestmark = pytest.mark.django_db


def _auth(client: APIClient, user: Utilisateur) -> APIClient:
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def client_tenant():
    client = APIClient()
    client.defaults["HTTP_HOST"] = HOTE
    return client


@pytest.fixture
def env_test(db):
    """Initialise l'environnement de test tenant."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="Client Invest BTP",
            defaults={"type_tiers": TypeTiers.ENTREPRISE, "ville": "Abidjan"},
        )

        def creer_user(email, nom, prenom, role, is_owner=False):
            u, _ = Utilisateur.tous_objets.get_or_create(
                email=email,
                defaults={
                    "nom": nom,
                    "prenom": prenom,
                    "role_global": role,
                    "statut": StatutUtilisateur.ACTIF,
                    "is_owner": is_owner,
                },
            )
            u.role_global = role
            u.is_owner = is_owner
            u.password = make_password(MOT_DE_PASSE)
            u.save()
            return u

        dg = creer_user("dg.testcp@demo.ci", "Kouamé", "Patrice", RoleGlobal.DIRECTEUR_GENERAL, is_owner=True)
        admin = creer_user("admin.testcp@demo.ci", "Kouassi", "Admin", RoleGlobal.ADMIN, is_owner=False)
        cp = creer_user("cp.testcp@demo.ci", "Diallo", "Amadou", RoleGlobal.CHEF_PROJET)
        ct = creer_user("ct.testcp@demo.ci", "Soro", "Mamadou", RoleGlobal.CONDUCTEUR_TRAVAUX)
        collab = creer_user("collab.testcp@demo.ci", "Koné", "Affoué", RoleGlobal.CHEF_CHANTIER)

        projet = Projet.objects.create(
            reference="PRJ-TEST-CP-01",
            nom="Résidence Test Initial CP",
            client=client_tiers,
            ville="Abidjan",
            chef_projet=cp,
            conducteur_travaux=ct,
            date_debut_prevue=date.today() + timedelta(days=1),
            date_fin_prevue=date.today() + timedelta(days=90),
            budget_initial_montant=15000000,
            statut=StatutProjet.EN_ATTENTE,
        )
        AffectationProjet.objects.create(
            projet=projet,
            utilisateur=cp,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        )
        AffectationProjet.objects.create(
            projet=projet,
            utilisateur=ct,
            role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
            est_actif=True,
        )

        return {
            "dg": dg,
            "admin": admin,
            "cp": cp,
            "ct": ct,
            "collab": collab,
            "client_tiers": client_tiers,
            "projet": projet,
        }


def test_creation_projet_sans_chef_projet_succes_dg(client_tenant, env_test):
    """Le DG peut créer un chantier sans aucun Chef de Projet (chef_projet nullable)."""
    dg = env_test["dg"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, dg)
    demain = date.today() + timedelta(days=2)
    fin = demain + timedelta(days=60)

    payload = {
        "nom": "Villa Riviera Sans CP",
        "client": str(tiers_client.id),
        "ville": "Abidjan",
        "quartier": "Riviera Golf",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
        "budget_initial_montant": 25_000_000_00,
        "description": "Chantier en phase préparatoire",
    }

    rep = cl.post("/api/v1/projets/", payload, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    projet_id = data["id"]

    assert data["nom"] == "Villa Riviera Sans CP"
    assert data["chef_projet"] is None
    assert data["conducteur_travaux"] is None

    with schema_context(SCHEMA):
        projet = Projet.objects.get(id=projet_id)
        assert projet.chef_projet is None
        assert not AffectationProjet.objects.filter(
            projet=projet, role_projet=RoleProjet.CHEF_PROJET
        ).exists()


def test_creation_projet_avec_conducteur_travaux_seul_sans_hack(client_tenant, env_test):
    """Créer un projet avec seulement un CT ne promeut plus ce CT en Chef de Projet."""
    admin = env_test["admin"]
    ct = env_test["ct"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, admin)
    demain = date.today() + timedelta(days=3)
    fin = demain + timedelta(days=90)

    payload = {
        "nom": "Immeuble Indigo CT Seul",
        "client": str(tiers_client.id),
        "ville": "San-Pédro",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
        "conducteur_travaux_id": str(ct.id),
    }

    rep = cl.post("/api/v1/projets/", payload, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    projet_id = data["id"]

    assert data["chef_projet"] is None
    assert data["conducteur_travaux"]["id"] == str(ct.id)

    with schema_context(SCHEMA):
        projet = Projet.objects.get(id=projet_id)
        assert projet.chef_projet is None
        assert projet.conducteur_travaux == ct
        # L'affectation doit être de type CONDUCTEUR_TRAVAUX et non CHEF_PROJET
        aff_ct = AffectationProjet.objects.filter(
            projet=projet, utilisateur=ct
        ).first()
        assert aff_ct is not None
        assert aff_ct.role_projet == RoleProjet.CONDUCTEUR_TRAVAUX
        assert not AffectationProjet.objects.filter(
            projet=projet, role_projet=RoleProjet.CHEF_PROJET
        ).exists()


def test_creation_projet_interdite_aux_non_dg_non_admin(client_tenant, env_test):
    """Un utilisateur non-DG et non-Admin (ex: Chef de Projet) ne peut pas créer de projet (403)."""
    cp = env_test["cp"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, cp)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    payload = {
        "nom": "Projet Tentative CP",
        "client": str(tiers_client.id),
        "ville": "Abidjan",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
    }

    rep = cl.post("/api/v1/projets/", payload, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_detachement_chef_projet_via_patch(client_tenant, env_test):
    """Le PATCH {'chef_projet_id': null} détache le CP et désactive son affectation active."""
    admin = env_test["admin"]
    projet_db = env_test["projet"]
    cp = env_test["cp"]
    cl = _auth(client_tenant, admin)

    with schema_context(SCHEMA):
        assert projet_db.chef_projet == cp
        assert AffectationProjet.objects.filter(
            projet=projet_db, utilisateur=cp, est_actif=True
        ).exists()

    url = f"/api/v1/projets/{projet_db.id}/"
    rep = cl.patch(url, {"chef_projet_id": None}, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["chef_projet"] is None

    with schema_context(SCHEMA):
        projet_db.refresh_from_db()
        assert projet_db.chef_projet is None
        aff = AffectationProjet.objects.get(projet=projet_db, utilisateur=cp)
        assert aff.est_actif is False


def test_assignation_nouveau_cp_sur_projet_sans_cp(client_tenant, env_test):
    """Un projet créé sans CP peut recevoir un CP ultérieurement via PATCH."""
    admin = env_test["admin"]
    cp = env_test["cp"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, admin)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=40)

    # 1. Création sans CP
    rep_create = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Chantier Étape 1 Sans CP",
            "client": str(tiers_client.id),
            "ville": "Bouaké",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_create.status_code == status.HTTP_201_CREATED
    projet_id = rep_create.json()["id"]

    # 2. Assignation d'un CP via PATCH
    url = f"/api/v1/projets/{projet_id}/"
    rep_patch = cl.patch(url, {"chef_projet_id": str(cp.id)}, format="json", HTTP_HOST=HOTE)
    assert rep_patch.status_code == status.HTTP_200_OK
    data = rep_patch.json()
    assert data["chef_projet"]["id"] == str(cp.id)

    with schema_context(SCHEMA):
        projet = Projet.objects.get(id=projet_id)
        assert projet.chef_projet == cp
        assert AffectationProjet.objects.filter(
            projet=projet,
            utilisateur=cp,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        ).exists()


def test_gouvernance_equipe_sur_projet_sans_cp(client_tenant, env_test):
    """Sur un chantier sans CP, seule la Direction peut gérer l'équipe (403 pour un conducteur)."""
    dg = env_test["dg"]
    ct = env_test["ct"]
    collab = env_test["collab"]
    tiers_client = env_test["client_tiers"]

    # 1. Création du projet sans CP par le DG
    cl_dg = _auth(client_tenant, dg)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=45)

    rep = cl_dg.post(
        "/api/v1/projets/",
        {
            "nom": "Chantier Gouvernance Direction",
            "client": str(tiers_client.id),
            "ville": "Yamoussoukro",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    projet_id = rep.json()["id"]

    # 2. Le DG affecte le CT en Conducteur de Travaux
    rep_aff_ct = cl_dg.post(
        f"/api/v1/projets/{projet_id}/affectations/",
        {
            "utilisateur_id": str(ct.id),
            "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_aff_ct.status_code == status.HTTP_201_CREATED

    # 3. Le Conducteur de Travaux (non CP, non Direction) tente d'affecter un autre membre -> 403 Forbidden
    cl_ct = _auth(APIClient(), ct)
    rep_refus = cl_ct.post(
        f"/api/v1/projets/{projet_id}/affectations/",
        {
            "utilisateur_id": str(collab.id),
            "role_projet": RoleProjet.CHEF_CHANTIER,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_refus.status_code == status.HTTP_403_FORBIDDEN


def test_tableau_de_bord_direction_avec_chantier_sans_cp(client_tenant, env_test):
    """Le tableau de bord ne crashe pas si des chantiers n'ont aucun chef de projet."""
    dg = env_test["dg"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, dg)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    # Création d'un chantier sans CP
    cl.post(
        "/api/v1/projets/",
        {
            "nom": "Chantier Dashboard Sans CP",
            "client": str(tiers_client.id),
            "ville": "Man",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
        },
        format="json",
        HTTP_HOST=HOTE,
    )

    # Appel du tableau de bord
    rep_tb = cl.get("/api/v1/tableau-de-bord/", HTTP_HOST=HOTE)
    assert rep_tb.status_code == status.HTTP_200_OK
    data = rep_tb.json()
    assert "projets" in data
    projet_sans_cp_data = next(
        p for p in data["projets"] if p["nom"] == "Chantier Dashboard Sans CP"
    )
    assert projet_sans_cp_data["chef_projet_nom"] is None


def test_evolution_statut_chantier_sans_cp(client_tenant, env_test):
    """Un chantier sans CP peut passer au statut EN_COURS ou TERMINE sans blocage."""
    dg = env_test["dg"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, dg)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    rep = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Chantier Statut Test",
            "client": str(tiers_client.id),
            "ville": "Korhogo",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    projet_id = rep.json()["id"]

    # Passage à EN_COURS
    url = f"/api/v1/projets/{projet_id}/"
    rep_en_cours = cl.patch(url, {"statut": StatutProjet.EN_COURS}, format="json", HTTP_HOST=HOTE)
    assert rep_en_cours.status_code == status.HTTP_200_OK
    assert rep_en_cours.json()["statut"] == StatutProjet.EN_COURS

    # Passage à TERMINE
    rep_termine = cl.patch(url, {"statut": StatutProjet.TERMINE}, format="json", HTTP_HOST=HOTE)
    assert rep_termine.status_code == status.HTTP_200_OK
    assert rep_termine.json()["statut"] == StatutProjet.TERMINE
