"""Optional project manager: form creation and dedicated team management.

Creation has no team fields. Assignments are managed through their own routes.
The public CRUD rejects status changes, and dashboards handle missing managers.
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

        dg = creer_user(
            "dg.testcp@demo.ci", "Kouamé", "Patrice", RoleGlobal.DIRECTEUR_GENERAL, is_owner=True
        )
        admin = creer_user(
            "admin.testcp@demo.ci", "Kouassi", "Admin", RoleGlobal.ADMIN, is_owner=False
        )
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
        "maitre_ouvrage": tiers_client.raison_sociale,
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Abidjan",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
        "budget_initial_montant": 25_000_000_00,
        "description": "Chantier en phase préparatoire",
    }

    rep = cl.post("/api/v1/projets/", payload, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    projet_id = rep["Location"].rstrip("/").split("/")[-1]

    assert data["nom"] == "Villa Riviera Sans CP"
    assert "chef_projet" not in data
    assert "conducteur_travaux" not in data

    with schema_context(SCHEMA):
        projet = Projet.objects.get(id=projet_id)
        assert projet.chef_projet is None
        assert not AffectationProjet.objects.filter(
            projet=projet, role_projet=RoleProjet.CHEF_PROJET
        ).exists()


def test_creation_projet_puis_affectation_ct_sans_cp(client_tenant, env_test):
    cl = _auth(client_tenant, env_test["admin"])
    rep = cl.post(
        "/api/v1/projets/",
        {
            "nom": "CT seul",
            "type_projet": "BATIMENT_RESIDENTIEL",
            "maitre_ouvrage": "Client",
            "ville": "Man",
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep.status_code == 201
    url = rep["Location"]
    rep_aff = cl.post(
        url + "affectations/",
        {
            "utilisateur_id": str(env_test["ct"].pk),
            "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_aff.status_code == 201, rep_aff.data
    with schema_context(SCHEMA):
        projet = Projet.objects.get(reference=rep.data["reference"])
        assert projet.chef_projet_id is None
        assert projet.conducteur_travaux_id == env_test["ct"].pk
        assert not projet.affectations.filter(role_projet=RoleProjet.CHEF_PROJET).exists()


def test_creation_projet_interdite_aux_non_dg_non_admin(client_tenant, env_test):
    """Un utilisateur non-DG et non-Admin (ex: Chef de Projet) ne peut pas créer de projet (403)."""
    cp = env_test["cp"]
    tiers_client = env_test["client_tiers"]
    cl = _auth(client_tenant, cp)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    payload = {
        "nom": "Projet Tentative CP",
        "maitre_ouvrage": tiers_client.raison_sociale,
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Abidjan",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
    }

    rep = cl.post("/api/v1/projets/", payload, format="json", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_detachement_chef_projet_via_affectation(client_tenant, env_test):
    cl = _auth(client_tenant, env_test["admin"])
    with schema_context(SCHEMA):
        projet = env_test["projet"]
        aff = AffectationProjet.objects.get(projet=projet, utilisateur=env_test["cp"])
    rep = cl.patch(
        f"/api/v1/projets/{projet.pk}/affectations/{aff.pk}/",
        {"est_actif": False},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep.status_code == 200, rep.data
    with schema_context(SCHEMA):
        projet.refresh_from_db()
        aff.refresh_from_db()
        assert projet.chef_projet_id is None
        assert not aff.est_actif


def test_assignation_nouveau_cp_sur_projet_sans_cp(client_tenant, env_test):
    cl = _auth(client_tenant, env_test["admin"])
    rep = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Sans CP",
            "type_projet": "BATIMENT_RESIDENTIEL",
            "maitre_ouvrage": "Client",
            "ville": "Man",
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep.status_code == 201
    assigned = cl.post(
        rep["Location"] + "affectations/",
        {
            "utilisateur_id": str(env_test["cp"].pk),
            "role_projet": RoleProjet.CHEF_PROJET,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert assigned.status_code == 201, assigned.data
    with schema_context(SCHEMA):
        projet = Projet.objects.get(reference=rep.data["reference"])
        assert projet.chef_projet_id == env_test["cp"].pk
        assert projet.affectations.filter(utilisateur=env_test["cp"], est_actif=True).exists()


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
            "maitre_ouvrage": tiers_client.raison_sociale,
            "type_projet": "BATIMENT_RESIDENTIEL",
            "ville": "Yamoussoukro",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    projet_id = rep["Location"].rstrip("/").split("/")[-1]

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

    # Un conducteur ne peut pas affecter un autre membre.
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
            "maitre_ouvrage": tiers_client.raison_sociale,
            "type_projet": "BATIMENT_RESIDENTIEL",
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


def test_statut_hors_formulaire_refuse(client_tenant, env_test):
    cl = _auth(client_tenant, env_test["dg"])
    rep = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Sans CP",
            "type_projet": "BATIMENT_RESIDENTIEL",
            "maitre_ouvrage": "Client",
            "ville": "Man",
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep.status_code == 201
    for statut in [StatutProjet.EN_COURS, StatutProjet.TERMINE]:
        refused = cl.patch(rep["Location"], {"statut": statut}, format="json", HTTP_HOST=HOTE)
        assert refused.status_code == 400
    with schema_context(SCHEMA):
        projet = Projet.objects.get(reference=rep.data["reference"])
        assert projet.statut == StatutProjet.EN_ATTENTE
        assert projet.chef_projet_id is None
