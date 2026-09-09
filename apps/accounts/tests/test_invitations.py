"""Tests de validation du modèle et des services d'invitation (MLD §5.2)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.accounts.services.invitations import (
    accepter_invitation,
    creer_invitation,
    obtenir_invitation_par_jeton,
)
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def admin_invitant(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.invitant@demo.ci").delete()
        user = Utilisateur.objects.create_user(
            email="admin.invitant@demo.ci",
            password="AdminPassword123!",
            nom="Diallo",
            prenom="Amadou",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        yield user
        Invitation.objects.filter(emetteur=user).delete()
        Utilisateur.tous_objets.filter(pk=user.pk).delete()


@pytest.mark.django_db
def test_creer_invitation_service(admin_invitant):
    with schema_context(SCHEMA):
        mail.outbox = []
        invitation = creer_invitation(
            email="invite.test@demo.ci",
            role_propose=RoleGlobal.CHEF_PROJET,
            nom="Kouassi Yves",
            emetteur=admin_invitant,
            hote=HOTE,
        )

        assert invitation.nom == "Kouassi Yves"
        assert invitation.email == "invite.test@demo.ci"
        assert invitation.role_propose == RoleGlobal.CHEF_PROJET
        assert invitation.emetteur == admin_invitant
        assert invitation.statut == Invitation.Statut.ENVOYEE
        assert invitation.utilise_le is None
        assert not invitation.est_expiree
        assert invitation.est_utilisable

        # Empreinte SHA-256
        assert len(invitation.empreinte) == 64
        assert hasattr(invitation, "jeton_clair")
        assert Invitation.empreinte_de(invitation.jeton_clair) == invitation.empreinte

        # Délai de validité 72h
        assert invitation.expire_le > timezone.now() + timedelta(hours=71)

        # Envoi d'email avec fragment de jeton
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert "Kouassi Yves" in email.body
        assert f"#jeton={invitation.jeton_clair}" in email.body
        assert str(invitation.jeton_clair) not in invitation.empreinte


@pytest.mark.django_db
def test_obtenir_et_accepter_invitation(admin_invitant):
    with schema_context(SCHEMA):
        invitation = creer_invitation(
            email="collaborateur@demo.ci",
            role_propose=RoleGlobal.CONDUCTEUR_TRAVAUX,
            nom="Aka Marc",
            emetteur=admin_invitant,
        )
        jeton = invitation.jeton_clair

        # Recherche par jeton en clair
        trouvee = obtenir_invitation_par_jeton(jeton)
        assert trouvee is not None
        assert trouvee.pk == invitation.pk

        # Recherche avec mauvais jeton
        assert obtenir_invitation_par_jeton("00000000-0000-0000-0000-000000000000") is None

        # Acceptation
        succes = accepter_invitation(trouvee)
        assert succes is True
        trouvee.refresh_from_db()
        assert trouvee.statut == Invitation.Statut.ACCEPTEE
        assert trouvee.utilise_le is not None
        assert not trouvee.est_utilisable

        # Rejeu impossible
        assert accepter_invitation(trouvee) is False


@pytest.mark.django_db
def test_invitation_expiree(admin_invitant):
    with schema_context(SCHEMA):
        invitation = creer_invitation(
            email="retardataire@demo.ci",
            role_propose=RoleGlobal.VISITEUR,
            nom="Traore",
            emetteur=admin_invitant,
        )
        # Forcer expiration
        invitation.expire_le = timezone.now() - timedelta(hours=1)
        invitation.save()

        assert invitation.est_expiree is True
        assert invitation.est_utilisable is False

        succes = accepter_invitation(invitation)
        assert succes is False
        invitation.refresh_from_db()
        assert invitation.statut == Invitation.Statut.EXPIREE


@pytest.mark.django_db
def test_api_invitations_post_et_get(admin_invitant):
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=admin_invitant)

    # 1. Création via l'API
    payload = {
        "email": "nouveau.membre@demo.ci",
        "role_propose": "CT",
        "nom": "Bamba Salif",
    }
    rep_post = client.post("/api/v1/invitations/", payload, format="json")
    assert rep_post.status_code == status.HTTP_201_CREATED
    assert rep_post.data["nom"] == "Bamba Salif"
    assert rep_post.data["email"] == "nouveau.membre@demo.ci"
    assert rep_post.data["role_propose"] == "CT"
    assert "jeton" not in rep_post.data
    assert "empreinte" not in rep_post.data

    with schema_context(SCHEMA):
        inv_db = Invitation.objects.filter(email="nouveau.membre@demo.ci").first()
        assert inv_db is not None
        assert inv_db.nom == "Bamba Salif"
        assert inv_db.emetteur == admin_invitant
        assert len(inv_db.empreinte) == 64

    # 2. Liste via l'API
    rep_get = client.get("/api/v1/invitations/")
    assert rep_get.status_code == status.HTTP_200_OK
    assert isinstance(rep_get.data, list)
    assert any(
        inv["email"] == "nouveau.membre@demo.ci" and inv["nom"] == "Bamba Salif"
        for inv in rep_get.data
    )


@pytest.mark.django_db
def test_api_verifier_invitation_valide(admin_invitant):
    client = APIClient(headers={"host": HOTE})
    with schema_context(SCHEMA):
        invitation = creer_invitation(
            email="marie.test@demo.ci",
            role_propose=RoleGlobal.CHEF_PROJET,
            nom="Marie Kouassi",
            emetteur=admin_invitant,
            hote=HOTE,
        )
        jeton = invitation.jeton_clair

    # Appel anonyme (non authentifié)
    rep = client.post(
        "/api/v1/invitations/verifier/",
        {"jeton": str(jeton)},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data["email"] == "marie.test@demo.ci"
    assert rep.data["nom"] == "Marie Kouassi"
    assert rep.data["role_propose"] == RoleGlobal.CHEF_PROJET
    assert rep.data["role_libelle"] == "Chef de Projet"
    assert rep.data["expire_dans"] > 0
    assert "entreprise" in rep.data

    # Vérifie que le jeton n'a PAS été consommé
    with schema_context(SCHEMA):
        invitation.refresh_from_db()
        assert invitation.statut == Invitation.Statut.ENVOYEE
        assert invitation.utilise_le is None
        assert invitation.est_utilisable


@pytest.mark.django_db
def test_api_verifier_invitation_invalide_ou_expiree(admin_invitant):
    client = APIClient(headers={"host": HOTE})

    # Jeton inconnu
    rep_inconnu = client.post(
        "/api/v1/invitations/verifier/",
        {"jeton": "11111111-1111-1111-1111-111111111111"},
        format="json",
    )
    assert rep_inconnu.status_code == status.HTTP_410_GONE
    assert rep_inconnu.data["erreur"]["code"] == "jeton_expire"

    # Jeton expiré
    with schema_context(SCHEMA):
        inv_expiree = creer_invitation(
            email="expiree@demo.ci",
            role_propose=RoleGlobal.VISITEUR,
            nom="Test Expiré",
            emetteur=admin_invitant,
        )
        inv_expiree.expire_le = timezone.now() - timedelta(hours=2)
        inv_expiree.save()
        jeton_exp = inv_expiree.jeton_clair

    rep_exp = client.post(
        "/api/v1/invitations/verifier/",
        {"jeton": str(jeton_exp)},
        format="json",
    )
    assert rep_exp.status_code == status.HTTP_410_GONE
    assert rep_exp.data["erreur"]["code"] == "jeton_expire"


@pytest.mark.django_db
def test_api_accepter_invitation_mot_de_passe_faible(admin_invitant):
    client = APIClient(headers={"host": HOTE})
    with schema_context(SCHEMA):
        invitation = creer_invitation(
            email="faible@demo.ci",
            role_propose=RoleGlobal.CONDUCTEUR_TRAVAUX,
            nom="Faible Pwd",
            emetteur=admin_invitant,
        )
        jeton = invitation.jeton_clair

    rep = client.post(
        "/api/v1/invitations/accepter/",
        {
            "jeton": str(jeton),
            "nom": "Pwd",
            "prenom": "Faible",
            "mot_de_passe": "court",  # Trop court, manque chiffres et spéciaux
        },
        format="json",
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert rep.data["erreur"]["code"] == "validation"


@pytest.mark.django_db
def test_api_accepter_invitation_succes_et_acces_modules(admin_invitant):
    client = APIClient(headers={"host": HOTE})
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="nouveau.collab@demo.ci").delete()
        invitation = creer_invitation(
            email="nouveau.collab@demo.ci",
            role_propose=RoleGlobal.CHEF_CHANTIER,
            nom="Kouassi",
            emetteur=admin_invitant,
        )
        jeton = invitation.jeton_clair

    mot_de_passe_valide = "SuperSecurise2026!"
    rep = client.post(
        "/api/v1/invitations/accepter/",
        {
            "jeton": str(jeton),
            "nom": "Kouassi",
            "prenom": "Jean-Marc",
            "mot_de_passe": mot_de_passe_valide,
        },
        format="json",
    )

    assert rep.status_code == status.HTTP_200_OK
    assert "access" in rep.data
    assert "refresh" in rep.data
    assert "utilisateur" in rep.data
    assert rep.data["utilisateur"]["email"] == "nouveau.collab@demo.ci"
    assert rep.data["utilisateur"]["nom"] == "Kouassi"
    assert rep.data["utilisateur"]["prenom"] == "Jean-Marc"
    # **Le rôle activé est celui de l'invitation** — ici Chef de Chantier.
    #
    # *Cette ligne exigeait `ADMIN`, et verrouillait ainsi le défaut qu'elle
    # aurait dû interdire : `accepter_invitation` écrasait le rôle choisi, si
    # bien que toute personne invitée devenait administratrice de l'entreprise.
    # Un test qui décrit le comportement observé au lieu du comportement voulu
    # transforme un défaut en spécification.*
    assert rep.data["utilisateur"]["role_global"] == RoleGlobal.CHEF_CHANTIER
    assert rep.data["utilisateur"]["role_libelle"] == "Chef de Chantier"

    # Vérifie en base de données
    with schema_context(SCHEMA):
        invitation.refresh_from_db()
        assert invitation.statut == Invitation.Statut.ACCEPTEE
        assert invitation.utilise_le is not None
        assert not invitation.est_utilisable

        user_db = Utilisateur.objects.filter(email="nouveau.collab@demo.ci").first()
        assert user_db is not None
        assert user_db.statut == StatutUtilisateur.ACTIF
        assert user_db.is_active is True
        assert user_db.check_password(mot_de_passe_valide) is True
        assert user_db.role_global == RoleGlobal.CHEF_CHANTIER
        # Une personne invitée n'hérite ni du statut de fondateur, ni de la
        # direction : c'est ce que l'écrasement en `ADMIN` lui donnait.
        assert user_db.is_owner is False
        assert user_db.is_dg is False

        # L'accès aux modules passe désormais par la matrice de son rôle, et
        # non plus par le court-circuit `ADMIN`. Le semis de cette matrice est
        # éprouvé par `test_initialiser_roles_par_defaut` ; son appel appartient
        # à la création de l'entreprise, pas à l'invitation.

    # Vérifie que la connexion via identifiants fonctionne immédiatement
    rep_login = client.post(
        "/api/v1/auth/token/",
        {"email": "nouveau.collab@demo.ci", "mot_de_passe": mot_de_passe_valide},
        format="json",
    )
    assert rep_login.status_code == status.HTTP_200_OK
    assert "access" in rep_login.data

    # Rejeu interdit
    rep_rejeu = client.post(
        "/api/v1/invitations/accepter/",
        {
            "jeton": str(jeton),
            "nom": "Kouassi",
            "prenom": "Jean-Marc",
            "mot_de_passe": mot_de_passe_valide,
        },
        format="json",
    )
    assert rep_rejeu.status_code == status.HTTP_410_GONE
