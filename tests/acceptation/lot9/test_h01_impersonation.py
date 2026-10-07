"""Tests de la règle H-01 (Impersonation et assistance Super Admin en lecture seule stricte).

H-01 : Session d'assistance limitée à 1 heure, lecture seule absolue (blocage écritures 403),
traçabilité double (JournalPlateforme & JournalAudit), e-mail au DG au démarrage (on_commit).
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from fabriques_lot9 import HOTE_CLIENT_A, HOST


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_super_admin_demarre_session_jeton_read_only(fab):
    """[H-01] Un super admin démarre une session d'assistance et reçoit un jeton avec claims read_only et is_impersonation."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()

    res = fab.demarrer_assistance(client_admin, ea, motif="Assistance technique client A")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "access" in data
    assert data["impersonation"]["mode"] == "LECTURE_SEULE"
    assert data["expire_dans"] == 3600


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_non_super_admin_refuse_403(fab):
    """[H-01] Un utilisateur client (DG, AD, etc.) ne peut pas démarrer une session d'assistance (403)."""
    ea = fab.entreprise_a()
    client_dg = fab.client_pour("DG")

    res = client_dg.post(f"/api/v1/admins/entreprises/{ea.id}/assistance/", {"motif": "Tentative illégitime"}, format="json")
    assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_lectures_autorisees_avec_jeton_assistance(fab):
    """[H-01] Avec le jeton d'assistance : les lectures GET sont autorisées (200)."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()
    res_start = fab.demarrer_assistance(client_admin, ea, motif="Assistance consultation")
    token = res_start.json()["access"]

    client_assist = APIClient(HTTP_HOST=HOST)
    client_assist.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    res_projets = client_assist.get("/api/v1/projets/")
    assert res_projets.status_code == status.HTTP_200_OK

    res_ent = client_assist.get("/api/v1/entreprise/")
    assert res_ent.status_code == status.HTTP_200_OK


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_ecritures_refusees_403_ecriture_interdite_assistance(fab):
    """[H-01] Avec le jeton d'assistance : POST, PUT, PATCH, DELETE sont refusés en 403 ecriture_interdite_assistance."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()
    res_start = fab.demarrer_assistance(client_admin, ea, motif="Assistance écriture bloquée")
    token = res_start.json()["access"]

    client_assist = APIClient(HTTP_HOST=HOST)
    client_assist.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Tentative POST
    res_post = client_assist.post("/api/v1/projets/", {"nom": "Chantier Fraude"}, format="json")
    assert res_post.status_code == status.HTTP_403_FORBIDDEN
    assert res_post.json()["erreur"]["code"] == "ecriture_interdite_assistance"

    # Tentative PATCH
    res_patch = client_assist.patch("/api/v1/entreprise/", {"nom_commercial": "Nom Piraté"}, format="json")
    assert res_patch.status_code == status.HTTP_403_FORBIDDEN
    assert res_patch.json()["erreur"]["code"] == "ecriture_interdite_assistance"

    # Tentative DELETE
    res_del = client_assist.delete("/api/v1/parametres/collaborateurs/00000000-0000-0000-0000-000000000001/")
    assert res_del.status_code == status.HTTP_403_FORBIDDEN
    assert res_del.json()["erreur"]["code"] == "ecriture_interdite_assistance"


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_deconnexion_assistance_autorisee(fab):
    """[H-01] Avec le jeton d'assistance : la déconnexion explicite d'assistance est autorisée."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()
    res_start = fab.demarrer_assistance(client_admin, ea, motif="Assistance déconnexion")
    token = res_start.json()["access"]

    client_assist = APIClient(HTTP_HOST=HOST)
    client_assist.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    res_logout = client_assist.post("/api/v1/admins/assistance/deconnexion/", format="json")
    assert res_logout.status_code == status.HTTP_200_OK


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_jeton_expire_apres_une_heure_refuse_401(fab):
    """[H-01] Le jeton d'assistance est refusé après expiration (401)."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()
    res_start = fab.demarrer_assistance(client_admin, ea, motif="Assistance expiration")
    token = res_start.json()["access"]

    # Falsification de l'expiration du jeton pour simuler 3601 secondes
    import jwt
    from django.conf import settings
    payload = jwt.decode(token, options={"verify_signature": False})
    payload["exp"] = payload["iat"] - 10
    expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    client_assist = APIClient(HTTP_HOST=HOST)
    client_assist.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")

    res = client_assist.get("/api/v1/projets/")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.carac
@pytest.mark.django_db
def test_h01_debut_session_trace_dans_les_deux_journaux(fab):
    """[H-01] Le début de session d'assistance est tracé dans JournalPlateforme et JournalAudit."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()

    nb_plat_avant = len(fab.entrees_journal_plateforme())
    nb_audit_avant = len(fab.entrees_audit(ea))

    res = fab.demarrer_assistance(client_admin, ea, motif="Assistance double trace")
    assert res.status_code == status.HTTP_200_OK

    nb_plat_apres = len(fab.entrees_journal_plateforme())
    nb_audit_apres = len(fab.entrees_audit(ea))

    assert nb_plat_apres == nb_plat_avant + 1
    assert nb_audit_apres == nb_audit_avant + 1


@pytest.mark.regle
@pytest.mark.django_db
def test_h01_fin_session_trace_dans_les_deux_journaux(fab):
    """[H-01] La clôture de session d'assistance est tracée avec entrée de fin dans les deux journaux."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()
    res_start = fab.demarrer_assistance(client_admin, ea, motif="Assistance clôture trace")
    token = res_start.json()["access"]

    client_assist = APIClient(HTTP_HOST=HOST)
    client_assist.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    nb_plat_avant = len(fab.entrees_journal_plateforme())
    nb_audit_avant = len(fab.entrees_audit(ea))

    res_close = client_assist.post("/api/v1/admins/assistance/deconnexion/", format="json")
    assert res_close.status_code == status.HTTP_200_OK

    nb_plat_apres = len(fab.entrees_journal_plateforme())
    nb_audit_apres = len(fab.entrees_audit(ea))

    assert nb_plat_apres == nb_plat_avant + 1
    assert nb_audit_apres == nb_audit_avant + 1


@pytest.mark.regle
@pytest.mark.django_db
def test_h01_debut_session_email_au_dg_apres_commit(fab):
    """[H-01] Au début de la session d'assistance, un e-mail part au DG (on_commit) avec l'adresse du super admin."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()

    res = fab.demarrer_assistance(client_admin, ea, motif="Assistance avec notification DG")
    assert res.status_code == status.HTTP_200_OK
    fab.valider_transaction()

    courriels = fab.courriels_envoyes()
    assert len(courriels) >= 1
    dernier = courriels[-1]
    assert "Session d'assistance ouverte sur votre espace" in dernier.subject
    assert client_admin.admin_user.email in dernier.body


@pytest.mark.regle
@pytest.mark.django_db
def test_h01_session_entreprise_sans_dg_ouvert_sans_email(fab):
    """[H-01] Session sur une entreprise sans DG actif : la session s'ouvre normalement sans générer d'e-mail."""
    ea = fab.entreprise_a()
    with schema_context(ea.schema_name):
        from apps.accounts.models import Utilisateur
        from apps.core.enums import StatutUtilisateur, RoleGlobal
        Utilisateur.objects.filter(role_global=RoleGlobal.DIRECTEUR_GENERAL).update(statut=StatutUtilisateur.DESACTIVE, is_active=False)
        Utilisateur.objects.filter(is_owner=True).update(statut=StatutUtilisateur.DESACTIVE, is_active=False)

    client_admin = fab.client_super_admin()
    nb_emails_avant = len(fab.courriels_envoyes())

    res = fab.demarrer_assistance(client_admin, ea, motif="Assistance sans DG actif")
    assert res.status_code == status.HTTP_200_OK
    fab.valider_transaction()

    assert len(fab.courriels_envoyes()) == nb_emails_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_h01_renouvellement_jeton_assistance_refuse(fab):
    """[H-01] Le renouvellement d'un jeton d'assistance est formellement refusé (L9-6)."""
    ea = fab.entreprise_a()
    client_admin = fab.client_super_admin()
    res_start = fab.demarrer_assistance(client_admin, ea, motif="Assistance non renouvelable")
    token = res_start.json()["access"]

    client = APIClient(HTTP_HOST=HOST)
    res_ref = client.post("/api/v1/auth/token/refresh/", {"refresh": token}, format="json")
    assert res_ref.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST)
