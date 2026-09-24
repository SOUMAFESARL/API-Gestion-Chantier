"""Tests du cycle complet de réinitialisation de mot de passe Super Admin (Control Plane).

Vérifie :
1. Demande de réinitialisation pour un Super Admin valide
   (202 Accepted, email envoyé, audit JournalPlateforme).
2. Demande pour un email inconnu ou non superuser (202 Accepted sans email, audit IGNORE).
3. Vérification de jeton valide sans consommation (règle R-32, 200 OK).
4. Vérification d'un jeton inexistant ou expiré (410 Gone).
5. Réinitialisation effective du mot de passe
   (200 OK, connexion avec nouveau mot de passe, consommation du jeton, audit).
6. Rejet du rejeu d'un jeton déjà consommé (410 Gone).
7. Rejet d'un mot de passe trop faible (400 Bad Request).
"""

import re

import pytest
from django.core import mail
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import JetonReinitialisation, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme

HOTE_PLATEFORME = "localhost"

DEMANDE_URL = "/api/v1/admins/mot-de-passe/demande/"
VERIFIER_URL = "/api/v1/admins/mot-de-passe/verifier/"
REINITIALISER_URL = "/api/v1/admins/mot-de-passe/reinitialiser/"
CONNEXION_URL = "/api/v1/admins/connexion/"

MOT_DE_PASSE_INITIAL = "InitialPassword123!"
NOUVEAU_MOT_DE_PASSE = "NouveauSecurise456!"


@pytest.fixture
def client_api():
    return APIClient(headers={"host": HOTE_PLATEFORME})


@pytest.fixture
def superuser_admin(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="admin.reset@ccd-digital.ci").delete()
        return Utilisateur.objects.create_superuser(
            email="admin.reset@ccd-digital.ci",
            password=MOT_DE_PASSE_INITIAL,
            nom="Directeur",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )


@pytest.fixture
def utilisateur_standard(db):
    """Crée un utilisateur non superuser dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="user.standard@ccd-digital.ci").delete()
        return Utilisateur.objects.create_user(
            email="user.standard@ccd-digital.ci",
            password="StandardPassword123!",
            nom="Standard",
            prenom="User",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
            is_staff=False,
            is_superuser=False,
        )


def _extraire_jeton_email() -> str:
    assert len(mail.outbox) > 0, "Aucun email n'a été envoyé."
    dernier_email = mail.outbox[-1]
    match = re.search(r"#jeton=([0-9a-f-]{36})", dernier_email.body)
    assert match, "Le lien de réinitialisation avec fragment #jeton= n'a pas été trouvé."
    return match.group(1)


@pytest.mark.django_db
def test_demande_reinitialisation_super_admin_succes(
    client_api, superuser_admin, django_capture_on_commit_callbacks
):
    """Une demande pour un Super Admin envoie un email et journalise l'audit."""
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_api.post(
            DEMANDE_URL,
            {"email": superuser_admin.email},
            format="json",
        )

    assert reponse.status_code == status.HTTP_202_ACCEPTED
    assert "expire_dans" in reponse.data
    assert reponse.data["expire_dans"] == 3600

    # Vérification de l'email
    assert len(mail.outbox) == 1
    email_envoye = mail.outbox[0]
    assert superuser_admin.email in email_envoye.to
    assert "/admin/mot-de-passe/definir#jeton=" in email_envoye.body

    # Vérification dans JournalPlateforme
    with schema_context(get_public_schema_name()):
        audit = (
            JournalPlateforme.objects.filter(
                action="DEMANDE_REINITIALISATION_SUPER_ADMIN",
                utilisateur_id=superuser_admin.id,
            )
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None
        assert audit.detail["email"] == superuser_admin.email
        assert audit.detail["statut"] == "SUCCES"


@pytest.mark.django_db
def test_demande_reinitialisation_email_inconnu_silence_defensif(
    client_api, django_capture_on_commit_callbacks
):
    """Un email inconnu renvoie 202 Accepted mais n'envoie aucun email."""
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_api.post(
            DEMANDE_URL,
            {"email": "inconnu@inconnu.ci"},
            format="json",
        )

    assert reponse.status_code == status.HTTP_202_ACCEPTED
    assert len(mail.outbox) == 0

    with schema_context(get_public_schema_name()):
        audit = (
            JournalPlateforme.objects.filter(
                action="DEMANDE_REINITIALISATION_SUPER_ADMIN",
                detail__email="inconnu@inconnu.ci",
            )
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None
        assert audit.detail["statut"] == "IGNORE"


@pytest.mark.django_db
def test_demande_reinitialisation_utilisateur_non_superuser_ignore(
    client_api, utilisateur_standard, django_capture_on_commit_callbacks
):
    """Un utilisateur qui n'a pas is_superuser=True ne reçoit aucun email."""
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_api.post(
            DEMANDE_URL,
            {"email": utilisateur_standard.email},
            format="json",
        )

    assert reponse.status_code == status.HTTP_202_ACCEPTED
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_verification_jeton_super_admin_sans_consommation(
    client_api, superuser_admin, django_capture_on_commit_callbacks
):
    """La vérification inspecte le jeton et ne le marque pas comme utilisé."""
    with django_capture_on_commit_callbacks(execute=True):
        client_api.post(DEMANDE_URL, {"email": superuser_admin.email}, format="json")

    jeton = _extraire_jeton_email()

    reponse = client_api.post(VERIFIER_URL, {"jeton": jeton}, format="json")
    assert reponse.status_code == status.HTTP_200_OK
    assert reponse.data["email"] == superuser_admin.email
    assert reponse.data["motif"] == "OUBLI"
    assert "admin/connexion" in reponse.data["url_connexion"]

    # Le jeton n'est pas consommé
    with schema_context(get_public_schema_name()):
        db_jeton = JetonReinitialisation.objects.get(
            empreinte=JetonReinitialisation.empreinte_de(jeton)
        )
        assert db_jeton.utilise_le is None
        assert db_jeton.est_utilisable is True


@pytest.mark.django_db
def test_verification_jeton_inexistant_410(client_api):
    """Un jeton non trouvé renvoie 410 Gone."""
    reponse = client_api.post(
        VERIFIER_URL,
        {"jeton": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_410_GONE
    assert reponse.data["erreur"]["code"] == "jeton_expire"


@pytest.mark.django_db
def test_reinitialisation_mot_de_passe_super_admin_succes(
    client_api, superuser_admin, django_capture_on_commit_callbacks
):
    """Réinitialisation réussie avec consommation du jeton, audit et nouvelle connexion."""
    with django_capture_on_commit_callbacks(execute=True):
        client_api.post(DEMANDE_URL, {"email": superuser_admin.email}, format="json")

    jeton = _extraire_jeton_email()
    mail.outbox.clear()

    # Réinitialisation
    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_api.post(
            REINITIALISER_URL,
            {"jeton": jeton, "mot_de_passe": NOUVEAU_MOT_DE_PASSE},
            format="json",
        )

    assert reponse.status_code == status.HTTP_200_OK
    assert "enregistré" in reponse.data["message"]

    # Le jeton est consommé
    with schema_context(get_public_schema_name()):
        db_jeton = JetonReinitialisation.objects.get(
            empreinte=JetonReinitialisation.empreinte_de(jeton)
        )
        assert db_jeton.utilise_le is not None

        # Audit présent
        audit = (
            JournalPlateforme.objects.filter(
                action="REINITIALISATION_MOT_DE_PASSE_SUPER_ADMIN",
                utilisateur_id=superuser_admin.id,
            )
            .order_by("-horodatage")
            .first()
        )
        assert audit is not None
        assert audit.detail["statut"] == "SUCCES"

    # Email de confirmation
    assert len(mail.outbox) == 1
    assert "modifié" in mail.outbox[0].subject

    # Connexion avec l'ancien mot de passe : rejetée (401)
    reponse_ancien = client_api.post(
        CONNEXION_URL,
        {"email": superuser_admin.email, "mot_de_passe": MOT_DE_PASSE_INITIAL},
        format="json",
    )
    assert reponse_ancien.status_code == status.HTTP_401_UNAUTHORIZED

    # Connexion avec le nouveau mot de passe : acceptée (200)
    reponse_nouveau = client_api.post(
        CONNEXION_URL,
        {"email": superuser_admin.email, "mot_de_passe": NOUVEAU_MOT_DE_PASSE},
        format="json",
    )
    assert reponse_nouveau.status_code == status.HTTP_200_OK
    assert "access" in reponse_nouveau.data


@pytest.mark.django_db
def test_reinitialisation_rejet_rejeu_jeton_consomme(
    client_api, superuser_admin, django_capture_on_commit_callbacks
):
    """Un jeton déjà consommé ne peut plus être rejoué (410 Gone)."""
    with django_capture_on_commit_callbacks(execute=True):
        client_api.post(DEMANDE_URL, {"email": superuser_admin.email}, format="json")

    jeton = _extraire_jeton_email()

    with django_capture_on_commit_callbacks(execute=True):
        client_api.post(
            REINITIALISER_URL,
            {"jeton": jeton, "mot_de_passe": NOUVEAU_MOT_DE_PASSE},
            format="json",
        )

    # Rejeu
    reponse_rejeu = client_api.post(
        REINITIALISER_URL,
        {"jeton": jeton, "mot_de_passe": "AutrePassword999!"},
        format="json",
    )
    assert reponse_rejeu.status_code == status.HTTP_410_GONE
    assert reponse_rejeu.data["erreur"]["code"] == "jeton_expire"


@pytest.mark.django_db
def test_reinitialisation_mot_de_passe_trop_faible(
    client_api, superuser_admin, django_capture_on_commit_callbacks
):
    """Un mot de passe trop court ou trop simple est rejeté en 400 Bad Request."""
    with django_capture_on_commit_callbacks(execute=True):
        client_api.post(DEMANDE_URL, {"email": superuser_admin.email}, format="json")

    jeton = _extraire_jeton_email()

    reponse = client_api.post(
        REINITIALISER_URL,
        {"jeton": jeton, "mot_de_passe": "123"},
        format="json",
    )
    assert reponse.status_code == status.HTTP_400_BAD_REQUEST

    # Le jeton reste non consommé
    with schema_context(get_public_schema_name()):
        db_jeton = JetonReinitialisation.objects.get(
            empreinte=JetonReinitialisation.empreinte_de(jeton)
        )
        assert db_jeton.utilise_le is None
