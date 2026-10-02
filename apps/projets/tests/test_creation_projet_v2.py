"""Tests du service interne de création de projet V2 (Wizard 3 étapes).

Couvre :
- Étape 1 : Informations générales, type de projet, maître d'œuvre, durée calculée
- Étape 2 : Lots (0 à N lots, modes d'exécution, types de bordereau)
- Étape 3 : Équipe (Chef de Projet responsable, Conducteur de Travaux distinct, CC, DF, Visiteurs)
- Règle R-DEMO-03 : DG interdit comme CP ou CT
- Personnalisation et unicité de la référence
- Atomicité transactionnelle
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.core.enums import (
    ModeExecution,
    RoleGlobal,
    RoleProjet,
    RoleTiersChoix,
    StatutProjet,
    StatutUtilisateur,
    TypeBordereau,
    TypeProjet,
    TypeTiers,
)
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.projets.tests.service_helpers import creer_projet_via_service
from apps.tiers.models import RoleTiers, Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def dg_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="dg.v2@demo.ci").delete()
        dg = Utilisateur.objects.create_user(
            email="dg.v2@demo.ci",
            password=MOT_DE_PASSE,
            nom="Kouamé",
            prenom="Patrice",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )
        yield dg
        Invitation.objects.all().delete()
        Lot.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=dg.pk).delete()


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.v2@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.v2@demo.ci",
            password=MOT_DE_PASSE,
            nom="Yao",
            prenom="Adjoua",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_owner=False,
        )
        yield admin
        Invitation.objects.all().delete()
        Lot.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=admin.pk).delete()


@pytest.fixture
def tiers_client(db):
    with schema_context(SCHEMA):
        tiers = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="SCI Les Lagunes V2",
            telephone="+2250102030405",
            ville="Abidjan",
        )
        RoleTiers.objects.create(tiers=tiers, role=RoleTiersChoix.CLIENT_MOA)
        return tiers


@pytest.fixture
def cp_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="cp.responsable@demo.ci").delete()
        cp = Utilisateur.objects.create_user(
            email="cp.responsable@demo.ci",
            password=MOT_DE_PASSE,
            nom="Djatchi",
            prenom="Kouamé",
            telephone="+2250701020304",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )
        yield cp
        Lot.objects.all().delete()
        AffectationProjet.objects.all().delete()
        Projet.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=cp.pk).delete()


@pytest.fixture
def ct_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="ct.terrain@demo.ci").delete()
        ct = Utilisateur.objects.create_user(
            email="ct.terrain@demo.ci",
            password=MOT_DE_PASSE,
            nom="Akpa",
            prenom="Brou Emmanuel",
            telephone="+2250705060708",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )
        yield ct
        Lot.objects.all().delete()
        AffectationProjet.objects.all().delete()
        Projet.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=ct.pk).delete()


@pytest.fixture
def cc_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="cc.chantier@demo.ci").delete()
        cc = Utilisateur.objects.create_user(
            email="cc.chantier@demo.ci",
            password=MOT_DE_PASSE,
            nom="Sidibé",
            prenom="Gbané Oumar",
            telephone="+2250709090909",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )
        yield cc
        AffectationProjet.objects.filter(utilisateur=cc).delete()
        Utilisateur.tous_objets.filter(pk=cc.pk).delete()


def auth_client(client, user):
    rep = client.post(
        "/api/v1/auth/token/",
        {"email": user.email, "mot_de_passe": MOT_DE_PASSE, "origine": "WEB"},
        format="json",
    )
    token = rep.data["access"]
    client.utilisateur_service = user
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_creation_projet_simple_sans_lot(client_tenant, admin_user, tiers_client, cp_user):
    """Test de création simple d'un projet avec 0 lot et responsable CP."""
    cl = auth_client(client_tenant, admin_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=90)

    payload = {
        "nom": "Projet Simple 0 Lot",
        "type_projet": TypeProjet.BATIMENT_RESIDENTIEL,
        "client": str(tiers_client.id),
        "maitre_oeuvre": "Cabinet Architec CI",
        "ville": "Cocody, Abidjan",
        "quartier": "Angré 8e Tranche",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
        "budget_initial_montant": 485_000_000_00,
        "description": "Projet test sans lot initial",
        "chef_projet_id": str(cp_user.id),
    }

    rep = creer_projet_via_service(cl, "/api/v1/projets/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()

    assert data["nom"] == "Projet Simple 0 Lot"
    assert data["type_projet"] == TypeProjet.BATIMENT_RESIDENTIEL
    assert data["maitre_oeuvre"] == "Cabinet Architec CI"
    assert data["lots"] == []
    assert data["duree_jours_ouvres"] > 0
    assert data["conducteur_travaux"] is None
    assert data["chef_projet"]["id"] == str(cp_user.id)
    assert data["statut"] == StatutProjet.EN_ATTENTE

    # Vérification de l'affectation projet
    with schema_context(SCHEMA):
        aff = AffectationProjet.objects.get(projet_id=data["id"], utilisateur=cp_user)
        assert aff.role_projet == RoleProjet.CHEF_PROJET


@pytest.mark.django_db
def test_creation_projet_complete_3_etapes(
    client_tenant, admin_user, tiers_client, cp_user, ct_user, cc_user
):
    """Test du Wizard complet : Métadonnées + 3 lots + Équipe complète."""
    cl = auth_client(client_tenant, admin_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=180)

    payload = {
        "nom": "Immeuble Les Palmiers R+5",
        "reference": "CCD-2025-007",
        "type_projet": TypeProjet.BATIMENT_COMMERCIAL,
        "client": str(tiers_client.id),
        "maitre_oeuvre": "BET Structure BTP",
        "ville": "Cocody, Abidjan",
        "quartier": "Danga",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
        "budget_initial_montant": 750_000_000_00,
        "description": "Construction complète R+5",
        "lots": [
            {
                "code": "L-01",
                "libelle": "Gros œuvre",
                "mode_execution": ModeExecution.REGIE,
                "type_bordereau": TypeBordereau.PRIX_UNITAIRE,
                "date_debut_prevue": str(demain),
                "date_fin_prevue": str(demain + timedelta(days=60)),
            },
            {
                "code": "L-02",
                "libelle": "Menuiserie aluminium",
                "mode_execution": ModeExecution.SOUS_TRAITANCE_STRUCTUREE,
                "type_bordereau": TypeBordereau.FORFAIT,
                "date_debut_prevue": str(demain + timedelta(days=61)),
                "date_fin_prevue": str(demain + timedelta(days=120)),
            },
            {
                "code": "L-03",
                "libelle": "Carrelage / Revêtements",
                "mode_execution": ModeExecution.SOUS_TRAITANCE_INFORMELLE,
                "type_bordereau": TypeBordereau.MIXTE,
                "date_debut_prevue": str(demain + timedelta(days=121)),
                "date_fin_prevue": str(fin),
            },
        ],
        "equipe": {
            "chef_projet_id": str(cp_user.id),
            "conducteur_travaux_id": str(ct_user.id),
            "chefs_chantier_ids": [str(cc_user.id)],
        },
    }

    rep = creer_projet_via_service(cl, "/api/v1/projets/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    projet_id = data["id"]

    assert data["reference"] == "CCD-2025-007"
    assert data["type_projet"] == TypeProjet.BATIMENT_COMMERCIAL
    assert len(data["lots"]) == 3
    assert data["chef_projet"]["id"] == str(cp_user.id)
    assert data["conducteur_travaux"]["id"] == str(ct_user.id)

    # Vérification en base des lots
    with schema_context(SCHEMA):
        lots = list(Lot.objects.filter(projet_id=projet_id).order_by("ordre"))
        assert len(lots) == 3
        assert lots[0].code == "L-01"
        assert lots[0].mode_execution == ModeExecution.REGIE
        assert lots[0].type_bordereau == TypeBordereau.PRIX_UNITAIRE

        assert lots[1].code == "L-02"
        assert lots[1].mode_execution == ModeExecution.SOUS_TRAITANCE_STRUCTUREE
        assert lots[1].type_bordereau == TypeBordereau.FORFAIT

        assert lots[2].code == "L-03"
        assert lots[2].mode_execution == ModeExecution.SOUS_TRAITANCE_INFORMELLE
        assert lots[2].type_bordereau == TypeBordereau.MIXTE

        # Vérification des affectations
        aff_cp = AffectationProjet.objects.get(projet_id=projet_id, utilisateur=cp_user)
        assert aff_cp.role_projet == RoleProjet.CHEF_PROJET

        aff_ct = AffectationProjet.objects.get(projet_id=projet_id, utilisateur=ct_user)
        assert aff_ct.role_projet == RoleProjet.CONDUCTEUR_TRAVAUX

        aff_cc = AffectationProjet.objects.get(projet_id=projet_id, utilisateur=cc_user)
        assert aff_cc.role_projet == RoleProjet.CHEF_CHANTIER


@pytest.mark.django_db
def test_reference_personnalisee_et_unicite(client_tenant, admin_user, tiers_client, cp_user):
    """Vérifie que la référence est modifiable mais unique par tenant."""
    cl = auth_client(client_tenant, admin_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    # 1. Premier projet avec référence personnalisée
    rep1 = creer_projet_via_service(
        cl,
        "/api/v1/projets/",
        {
            "nom": "Chantier Unique 1",
            "reference": "PRJ-CUSTOM-999",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_id": str(cp_user.id),
        },
        format="json",
    )
    assert rep1.status_code == status.HTTP_201_CREATED
    assert rep1.json()["reference"] == "PRJ-CUSTOM-999"

    # 2. Deuxième projet tentant d'utiliser la même référence -> 400
    rep2 = creer_projet_via_service(
        cl,
        "/api/v1/projets/",
        {
            "nom": "Chantier Doublon Référence",
            "reference": "PRJ-CUSTOM-999",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_id": str(cp_user.id),
        },
        format="json",
    )
    assert rep2.status_code == status.HTTP_400_BAD_REQUEST
    err_json = rep2.json()
    assert "reference" in err_json or "reference" in err_json.get("erreur", {}).get("details", {})


@pytest.mark.django_db
def test_invitation_cp_et_ct_a_la_volee(client_tenant, admin_user, tiers_client):
    """Invitation à la volée du CP et du CT avec création de compte et email."""
    cl = auth_client(client_tenant, admin_user)
    demain = date.today() + timedelta(days=2)
    fin = demain + timedelta(days=60)
    mail.outbox = []

    rep = creer_projet_via_service(
        cl,
        "/api/v1/projets/",
        {
            "nom": "Chantier avec CP et CT Invités",
            "client": str(tiers_client.id),
            "ville": "San Pedro",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "equipe": {
                "chef_projet_invite": {
                    "nom": "Kouadio",
                    "prenom": "Thierry",
                    "email": "t.kouadio@btp.ci",
                    "telephone": "+2250700000001",
                },
                "conducteur_travaux_invite": {
                    "nom": "Assi",
                    "prenom": "Kouamé",
                    "email": "k.assi@btp.ci",
                    "telephone": "+2250700000002",
                },
            },
        },
        format="json",
    )
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    projet_id = data["id"]

    # Vérification des utilisateurs créés
    with schema_context(SCHEMA):
        user_cp = Utilisateur.objects.get(email="t.kouadio@btp.ci")
        assert user_cp.role_global == RoleGlobal.CHEF_PROJET
        assert user_cp.statut == StatutUtilisateur.INVITE

        user_ct = Utilisateur.objects.get(email="k.assi@btp.ci")
        assert user_ct.role_global == RoleGlobal.CONDUCTEUR_TRAVAUX
        assert user_ct.statut == StatutUtilisateur.INVITE

        # Affectations
        aff_cp = AffectationProjet.objects.get(projet_id=projet_id, utilisateur=user_cp)
        assert aff_cp.role_projet == RoleProjet.CHEF_PROJET

        aff_ct = AffectationProjet.objects.get(projet_id=projet_id, utilisateur=user_ct)
        assert aff_ct.role_projet == RoleProjet.CONDUCTEUR_TRAVAUX

    # 2 emails d'invitations envoyés
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_dg_interdit_comme_cp_ou_ct(client_tenant, dg_user, admin_user, tiers_client, cp_user):
    """Le DG ne peut être ni Chef de Projet ni Conducteur de Travaux (R-DEMO-03)."""
    cl = auth_client(client_tenant, admin_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    # 1. DG comme CP
    rep1 = creer_projet_via_service(
        cl,
        "/api/v1/projets/",
        {
            "nom": "Test DG CP",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_id": str(dg_user.id),
        },
        format="json",
    )
    assert rep1.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert rep1.json()["erreur"]["code"] == "dg_non_assignable_comme_cp"

    # 2. DG comme CT
    rep2 = creer_projet_via_service(
        cl,
        "/api/v1/projets/",
        {
            "nom": "Test DG CT",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_id": str(cp_user.id),
            "conducteur_travaux_id": str(dg_user.id),
        },
        format="json",
    )
    assert rep2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert rep2.json()["erreur"]["code"] == "dg_non_assignable_comme_cp"


@pytest.mark.django_db
def test_atomicite_rollback_si_erreur_sur_lot(client_tenant, admin_user, tiers_client, cp_user):
    """Si un lot a une date de fin antérieure à sa date de début, rien n'est créé en base."""
    cl = auth_client(client_tenant, admin_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=60)

    payload = {
        "nom": "Projet Invalide Rollback",
        "client": str(tiers_client.id),
        "ville": "Abidjan",
        "date_debut_prevue": str(demain),
        "date_fin_prevue": str(fin),
        "chef_projet_id": str(cp_user.id),
        "lots": [
            {
                "code": "L-01",
                "libelle": "Lot Valide",
            },
            {
                "code": "L-02",
                "libelle": "Lot Invalide",
                "date_debut_prevue": str(demain + timedelta(days=20)),
                "date_fin_prevue": str(demain + timedelta(days=10)),  # Erreur !
            },
        ],
    }

    rep = creer_projet_via_service(cl, "/api/v1/projets/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST

    # Vérification que le projet n'a PAS été créé en base
    with schema_context(SCHEMA):
        assert not Projet.objects.filter(nom="Projet Invalide Rollback").exists()
