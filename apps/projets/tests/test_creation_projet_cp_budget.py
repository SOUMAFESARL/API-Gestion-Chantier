"""Tests pour la création de chantier avec CP obligatoire,
budget optionnel et règles DG (T-S1-05 & T-S1-08).
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, RoleTiersChoix, StatutUtilisateur, TypeTiers
from apps.projets.models import AffectationProjet, Projet
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
        Utilisateur.tous_objets.filter(email="dg.projet@demo.ci").delete()
        dg = Utilisateur.objects.create_user(
            email="dg.projet@demo.ci",
            password=MOT_DE_PASSE,
            nom="Kouamé",
            prenom="Patrice",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )
        yield dg
        Invitation.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=dg.pk).delete()


@pytest.fixture
def admin_delegue_user(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.delegue.prj@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.delegue.prj@demo.ci",
            password=MOT_DE_PASSE,
            nom="Yao",
            prenom="Adjoua",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            is_owner=False,
        )
        yield admin
        Invitation.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(pk=admin.pk).delete()


@pytest.fixture
def tiers_client(db):
    with schema_context(SCHEMA):
        tiers = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="SCI Les Lagunes",
            telephone="+2250102030405",
            ville="Abidjan",
        )
        RoleTiers.objects.create(tiers=tiers, role=RoleTiersChoix.CLIENT_MOA)
        return tiers


@pytest.fixture
def cp_existant(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="cp.existant@demo.ci").delete()
        cp = Utilisateur.objects.create_user(
            email="cp.existant@demo.ci",
            password=MOT_DE_PASSE,
            nom="Traoré",
            prenom="Ibrahim",
            telephone="+2250701020304",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )
        yield cp
        AffectationProjet.objects.filter(utilisateur=cp).delete()
        Projet.objects.filter(chef_projet=cp).delete()
        Utilisateur.tous_objets.filter(pk=cp.pk).delete()


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
def test_rec_s1_05_a_budget_null_accepte(
    client_tenant, admin_delegue_user, tiers_client, cp_existant
):
    """REC-S1-05-A : POST /api/v1/projets/ accepte budget_initial_montant: null."""
    cl = auth_client(client_tenant, admin_delegue_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=90)

    rep = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Projet Sans Budget Initial",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "budget_initial_montant": None,
            "chef_projet_id": str(cp_existant.id),
        },
        format="json",
    )

    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    assert data["budget_initial_montant"] is None
    assert data["budget_consomme_montant"] == 0
    assert data["nom"] == "Projet Sans Budget Initial"


@pytest.mark.django_db
def test_rec_s1_05_b_cp_obligatoire(client_tenant, admin_delegue_user, tiers_client):
    """REC-S1-05-B : L'assignation d'un CP est obligatoire
    (chef_projet_id ou chef_projet_invite).
    """
    cl = auth_client(client_tenant, admin_delegue_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=90)

    # Sans aucun CP
    rep_sans_cp = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Projet Sans CP",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "budget_initial_montant": 10_000_000,
        },
        format="json",
    )
    assert rep_sans_cp.status_code == status.HTTP_400_BAD_REQUEST
    assert rep_sans_cp.json()["erreur"]["code"] == "chef_projet_requis"

    # Avec les deux spécifiés en conflit
    rep_deux_cp = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Projet CP Conflit",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_id": "00000000-0000-0000-0000-000000000000",
            "chef_projet_invite": {
                "nom": "Koffi",
                "prenom": "Jean",
                "email": "j.koffi@demo.ci",
            },
        },
        format="json",
    )
    assert rep_deux_cp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_rec_s1_05_c_et_08_a_invitation_cp_et_mail_contextuel(client_tenant, dg_user, tiers_client):
    """REC-S1-05-C & REC-S1-08-A : Invitation CP à la volée, lien WhatsApp et email contextuel."""
    cl = auth_client(client_tenant, dg_user)
    demain = date.today() + timedelta(days=5)
    fin = demain + timedelta(days=120)

    mail.outbox = []

    rep = cl.post(
        "/api/v1/projets/",
        {
            "nom": "Résidence Les Merveilles",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "quartier": "Cocody Angré",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "budget_initial_montant": 65_000_000_00,
            "description": "Programme immobilier R+4",
            "chef_projet_invite": {
                "nom": "Soro",
                "prenom": "Mamadou",
                "email": "m.soro@btp-ci.com",
                "telephone": "+2250701020304",
            },
        },
        format="json",
    )

    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.json()
    projet_id = data["id"]

    # Vérification des détails CP et lien WhatsApp
    cp_data = data["chef_projet"]
    assert cp_data["nom"] == "Soro"
    assert cp_data["prenom"] == "Mamadou"
    assert cp_data["nom_complet"] == "Mamadou Soro"
    assert cp_data["email"] == "m.soro@btp-ci.com"
    assert cp_data["statut"] == "INVITE"
    assert cp_data["lien_whatsapp"] == "https://wa.me/2250701020304"

    # Vérification de l'affectation projet
    with schema_context(SCHEMA):
        user_cp = Utilisateur.objects.get(email="m.soro@btp-ci.com")
        assert user_cp.statut == StatutUtilisateur.INVITE
        assert AffectationProjet.objects.filter(
            projet_id=projet_id, utilisateur=user_cp, role_projet=RoleProjet.CONDUCTEUR_TRAVAUX
        ).exists()

        invitation = Invitation.objects.get(email="m.soro@btp-ci.com")
        assert invitation.statut == Invitation.Statut.ENVOYEE
        assert invitation.emetteur == dg_user

    # REC-S1-08-A : L'email mentionne explicitement le nom du chantier
    assert len(mail.outbox) == 1
    email_envoye = mail.outbox[0]
    assert "Résidence Les Merveilles" in email_envoye.subject
    assert "Résidence Les Merveilles" in email_envoye.body
    assert f"projet_id={projet_id}" in email_envoye.body
    assert f"next=/projets/{projet_id}" in email_envoye.body


@pytest.mark.django_db
def test_rec_s1_05_d_dg_interdit_comme_cp(client_tenant, dg_user, admin_delegue_user, tiers_client):
    """REC-S1-05-D : Le DG connecté ou ciblé ne peut pas être CP
    (422 dg_non_assignable_comme_cp).
    """
    # 1. Le DG essaie de s'assigner lui-même par son ID
    cl_dg = auth_client(client_tenant, dg_user)
    demain = date.today() + timedelta(days=1)
    fin = demain + timedelta(days=30)

    rep1 = cl_dg.post(
        "/api/v1/projets/",
        {
            "nom": "Tentative DG Auto-Assign",
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

    # 2. Le DG essaie de s'auto-inviter via son email
    rep2 = cl_dg.post(
        "/api/v1/projets/",
        {
            "nom": "Tentative DG Auto-Invite",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_invite": {
                "nom": dg_user.nom,
                "prenom": dg_user.prenom,
                "email": dg_user.email,
                "telephone": "+22501010101",
            },
        },
        format="json",
    )
    assert rep2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert rep2.json()["erreur"]["code"] == "dg_non_assignable_comme_cp"

    # 3. Un admin délégué tente de nommer le DG comme CP sur un chantier
    cl_admin = auth_client(client_tenant, admin_delegue_user)
    rep3 = cl_admin.post(
        "/api/v1/projets/",
        {
            "nom": "Tentative Admin Nomme DG",
            "client": str(tiers_client.id),
            "ville": "Abidjan",
            "date_debut_prevue": str(demain),
            "date_fin_prevue": str(fin),
            "chef_projet_id": str(dg_user.id),
        },
        format="json",
    )
    assert rep3.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert rep3.json()["erreur"]["code"] == "dg_non_assignable_comme_cp"
