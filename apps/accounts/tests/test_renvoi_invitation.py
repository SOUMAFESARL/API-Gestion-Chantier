"""Tests pour la tâche B2 du lot 3 : renvoi d'une invitation collaborateur."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.core.exceptions import QuotaPlanAtteint

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture(autouse=True)
def configuration_email():
    """S'assure que les emails sont capturés en mémoire pour les tests."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def dg_user(db):
    """Directeur Général (DG), is_owner=True."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="dg.renvoi@demo.ci",
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
            email="admin.renvoi@demo.ci",
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


def creer_invite_via_api(client, email="invite.renvoi@demo.ci", role="CC"):
    """Crée un collaborateur invité par l'API pour un état de départ réaliste."""
    url = "/api/v1/parametres/collaborateurs/"
    payload = {
        "email": email,
        "nom": "Kone",
        "prenom": "Ibrahim",
        "telephone": "+2250700000001",
        "role_global": role,
    }
    reponse = client.post(url, payload, format="json")
    assert reponse.status_code == status.HTTP_201_CREATED, reponse.data
    return reponse.data


@pytest.mark.django_db
def test_renvoi_emet_un_nouveau_lien(client_tenant, dg_user):
    """Vérifie le renvoi : 200, lien différent, et nouveau courriel envoyé."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="renvoi.lien@demo.ci")
    collab_id = creation["id"]
    ancien_lien = creation["lien_activation"]
    assert len(mail.outbox) == 1

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="renvoi.lien@demo.ci").update(
            cree_le=timezone.now() - timedelta(minutes=5)
        )

    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"
    reponse = client_tenant.post(url_renvoi, {}, format="json")

    assert reponse.status_code == status.HTTP_200_OK
    nouveau_lien = reponse.data["lien_activation"]
    assert nouveau_lien is not None
    assert nouveau_lien != ancien_lien
    assert reponse.data.get("email_envoye") is True
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_ancien_lien_revoque(client_tenant, dg_user):
    """L'ancienne invitation est REVOQUEE ; l'ancien jeton échoue, le nouveau réussit."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="renvoi.revoque@demo.ci")
    collab_id = creation["id"]
    ancien_jeton = creation["lien_activation"].split("#jeton=")[-1]

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="renvoi.revoque@demo.ci").update(
            cree_le=timezone.now() - timedelta(minutes=5)
        )

    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"
    reponse_renvoi = client_tenant.post(url_renvoi, {}, format="json")
    assert reponse_renvoi.status_code == status.HTTP_200_OK
    nouveau_jeton = reponse_renvoi.data["lien_activation"].split("#jeton=")[-1]

    with schema_context(SCHEMA):
        anciennes = Invitation.objects.filter(
            email="renvoi.revoque@demo.ci",
            statut=Invitation.Statut.REVOQUEE,
        )
        assert anciennes.exists()

    # Tentative d'acceptation avec l'ancien jeton (doit échouer)
    url_accepter = "/api/v1/invitations/accepter/"
    client_anonyme = APIClient(headers={"host": HOTE})
    rep_echec = client_anonyme.post(
        url_accepter,
        {
            "jeton": ancien_jeton,
            "mot_de_passe": "NouveauMdp123!",
            "nom": "Kone",
            "prenom": "Ibrahim",
        },
        format="json",
    )
    assert rep_echec.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_410_GONE)

    # Acceptation avec le nouveau jeton (doit réussir)
    rep_succes = client_anonyme.post(
        url_accepter,
        {
            "jeton": nouveau_jeton,
            "mot_de_passe": "NouveauMdp123!",
            "nom": "Kone",
            "prenom": "Ibrahim",
        },
        format="json",
    )
    assert rep_succes.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_renvoi_trop_rapproche_refuse(client_tenant, dg_user):
    """Deux renvois consécutifs en moins de 60s provoquent un 409 'patientez'."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="renvoi.trop.vite@demo.ci")
    collab_id = creation["id"]

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="renvoi.trop.vite@demo.ci").update(
            cree_le=timezone.now() - timedelta(minutes=5)
        )

    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"
    reponse1 = client_tenant.post(url_renvoi, {}, format="json")
    assert reponse1.status_code == status.HTTP_200_OK

    # 2e appel immédiat
    reponse2 = client_tenant.post(url_renvoi, {}, format="json")
    assert reponse2.status_code == status.HTTP_409_CONFLICT
    assert "patientez" in str(reponse2.data)


@pytest.mark.django_db
def test_invitation_expiree_se_renvoie(client_tenant, dg_user):
    """Une invitation expirée depuis 4 jours peut être renvoyée et le nouveau lien fonctionne."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="renvoi.expire@demo.ci")
    collab_id = creation["id"]

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="renvoi.expire@demo.ci").update(
            cree_le=timezone.now() - timedelta(days=4),
            expire_le=timezone.now() - timedelta(days=1),
        )

    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"
    reponse = client_tenant.post(url_renvoi, {}, format="json")
    assert reponse.status_code == status.HTTP_200_OK
    nouveau_jeton = reponse.data["lien_activation"].split("#jeton=")[-1]

    client_anonyme = APIClient(headers={"host": HOTE})
    rep_succes = client_anonyme.post(
        "/api/v1/invitations/accepter/",
        {
            "jeton": nouveau_jeton,
            "mot_de_passe": "MdpExpire123!",
            "nom": "Kone",
            "prenom": "Ibrahim",
        },
        format="json",
    )
    assert rep_succes.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_compte_actif_refuse(client_tenant, dg_user):
    """Un collaborateur actif ne peut pas recevoir de renvoi d'invitation (409)."""
    client_tenant.force_authenticate(user=dg_user)
    url_renvoi = f"/api/v1/parametres/collaborateurs/{dg_user.id}/renvoyer-invitation/"
    reponse = client_tenant.post(url_renvoi, {}, format="json")

    assert reponse.status_code == status.HTTP_409_CONFLICT
    assert "déjà activé" in str(reponse.data)


@pytest.mark.django_db
def test_renvoi_journalise(client_tenant, dg_user):
    """Le renvoi est consigné dans le JournalAudit avec geste=RENVOI."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="renvoi.audit@demo.ci")
    collab_id = creation["id"]

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="renvoi.audit@demo.ci").update(
            cree_le=timezone.now() - timedelta(minutes=5)
        )

    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"
    reponse = client_tenant.post(url_renvoi, {}, format="json")
    assert reponse.status_code == status.HTTP_200_OK

    with schema_context(SCHEMA):
        entree = JournalAudit.objects.filter(
            type_entite="invitation",
            valeur_apres__geste="RENVOI",
        ).latest("horodatage")
        assert entree is not None
        assert entree.utilisateur_id == dg_user.pk
        assert entree.valeur_apres.get("email") == "renvoi.audit@demo.ci"


@pytest.mark.django_db
def test_ad_ne_renvoie_pas_l_invitation_d_un_ad(client_tenant, dg_user, admin_user):
    """Un administrateur délégué (AD) ne peut pas renvoyer l'invitation d'un AD (403)."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="ad.invite@demo.ci", role="AD")
    collab_id = creation["id"]

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="ad.invite@demo.ci").update(
            cree_le=timezone.now() - timedelta(minutes=5)
        )

    # Tentative par l'AD
    client_tenant.force_authenticate(user=admin_user)
    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"
    reponse = client_tenant.post(url_renvoi, {}, format="json")

    assert reponse.status_code == status.HTTP_403_FORBIDDEN
    assert "Seul le Directeur Général a autorité pour inviter un administrateur." in str(
        reponse.data
    )


@pytest.mark.django_db
def test_quota_non_reverifie(client_tenant, dg_user):
    """Le renvoi ne doit pas échouer même si le quota d'utilisateurs du plan est atteint."""
    client_tenant.force_authenticate(user=dg_user)
    creation = creer_invite_via_api(client_tenant, email="renvoi.quota@demo.ci")
    collab_id = creation["id"]

    with schema_context(SCHEMA):
        Invitation.objects.filter(email="renvoi.quota@demo.ci").update(
            cree_le=timezone.now() - timedelta(minutes=5)
        )

    url_renvoi = f"/api/v1/parametres/collaborateurs/{collab_id}/renvoyer-invitation/"

    with patch(
        "apps.billing.services.quota.verifier_quota_avant_invitation",
        side_effect=QuotaPlanAtteint(
            detail="Limite atteinte", details={"limite": 3, "sieges_occupes": 3}
        ),
    ):
        reponse = client_tenant.post(url_renvoi, {}, format="json")
        assert reponse.status_code == status.HTTP_200_OK
        assert reponse.data["lien_activation"] is not None
