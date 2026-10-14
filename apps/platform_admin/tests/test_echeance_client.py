"""Tests pour la modification de l'échéance de l'abonnement d'un client (B2)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.billing.models import Abonnement, Plan
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import Entreprise

SCHEMA_CLIENT = "demo"
HOTE_PLATEFORME = "localhost"


@pytest.fixture(autouse=True)
def autoriser_ip_locale(settings):
    """Autorise l'adresse IP de test dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def client_api():
    """Client API configuré sur le domaine de la plateforme."""
    return APIClient(headers={"host": HOTE_PLATEFORME})


def _agent(email: str, superviseur: bool) -> Utilisateur:
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = (
            Utilisateur.objects.create_superuser if superviseur else Utilisateur.objects.create_user
        )
        return fabrique(
            email=email,
            password="MotDePasse12345!",
            nom="Agent",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            **({} if superviseur else {"is_staff": True}),
        )


@pytest.fixture
def super_admin_user(db):
    return _agent("superadmin.echeance@ccd-digital.ci", superviseur=True)


@pytest.fixture
def agent_support(db):
    return _agent("support.echeance@ccd-digital.ci", superviseur=False)


@pytest.fixture
def entreprise_test(db):
    """Prépare l'entreprise cliente demo avec les plans BTP et un abonnement actif."""
    with schema_context(get_public_schema_name()):
        p1, _ = Plan.objects.get_or_create(
            code=Plan.Code.BATISSEUR,
            defaults={
                "libelle": "Bâtisseur",
                "prix_mensuel_montant": 19_000_00,
                "limite_projets": 3,
                "limite_utilisateurs": 5,
            },
        )
        ent = Entreprise.objects.get(schema_name=SCHEMA_CLIENT)
        ent.statut = StatutEntreprise.ACTIF
        ent.save()

        ent.abonnements.all().delete()
        aujourdhui = timezone.now().date()
        Abonnement.objects.create(
            entreprise=ent,
            plan=p1,
            date_debut=aujourdhui - timedelta(days=30),
            date_fin=aujourdhui + timedelta(days=335),
            statut=Abonnement.Statut.ACTIF,
            renouvellement_auto=True,
        )

    with schema_context(SCHEMA_CLIENT):
        Utilisateur.tous_objets.filter(email="dg.demo@ccd.ci").delete()
        Utilisateur.objects.create_user(
            email="dg.demo@ccd.ci",
            password="MotDePasse12345!",
            nom="Directeur",
            prenom="General",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )

    return ent


@pytest.mark.django_db
def test_superviseur_repousse_l_echeance(client_api, super_admin_user, entreprise_test):
    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {
            "abonnement": {"date_fin": nouvelle_date},
            "motif": "Prolongation commerciale de test.",
        },
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["abonnement"]["date_fin"] == nouvelle_date
    with schema_context(get_public_schema_name()):
        abt = entreprise_test.abonnements.first()
        assert abt.date_fin.isoformat() == nouvelle_date
        assert abt.statut == Abonnement.Statut.ACTIF


@pytest.mark.django_db
def test_echeance_journalisee_plateforme_et_tenant(
    client_api, super_admin_user, entreprise_test
):
    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    motif = "Prolongation fidélité annuelle."
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}, "motif": motif},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK

    with schema_context(get_public_schema_name()):
        log_plat = JournalPlateforme.objects.filter(
            entreprise_id=entreprise_test.id, action="MODIFICATION_ECHEANCE"
        ).first()
        assert log_plat is not None
        assert log_plat.detail["motif"] == motif
        assert log_plat.detail["nouvelle_date_fin"] == nouvelle_date

    with schema_context(SCHEMA_CLIENT):
        log_tenant = JournalAudit.objects.filter(type_entite="Abonnement").first()
        assert log_tenant is not None
        assert log_tenant.action == "MODIFICATION"


@pytest.mark.django_db
def test_echeance_previent_le_dg_sans_le_motif(
    client_api, super_admin_user, entreprise_test, django_capture_on_commit_callbacks
):
    mail.outbox.clear()
    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    motif = "Motif ultra secret interne éditeur."

    with django_capture_on_commit_callbacks(execute=True):
        rep = client_api.patch(
            f"/api/v1/admins/clients/{entreprise_test.id}/",
            {"abonnement": {"date_fin": nouvelle_date}, "motif": motif},
            format="json",
            HTTP_HOST=HOTE_PLATEFORME,
        )
    assert rep.status_code == status.HTTP_200_OK
    assert len(mail.outbox) >= 1
    email = mail.outbox[0]
    assert motif not in email.body
    assert "date de fin de votre abonnement a été modifiée" in email.body


@pytest.mark.django_db
def test_en_essai_fin_essai_suit(client_api, super_admin_user, entreprise_test):
    with schema_context(get_public_schema_name()):
        abt = entreprise_test.abonnements.first()
        abt.statut = Abonnement.Statut.ESSAI
        abt.fin_essai = abt.date_fin
        abt.save()

    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=50)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}, "motif": "Prolongation période d'essai."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK
    with schema_context(get_public_schema_name()):
        abt.refresh_from_db()
        assert abt.date_fin.isoformat() == nouvelle_date
        assert abt.fin_essai.isoformat() == nouvelle_date


@pytest.mark.django_db
def test_date_passee_refusee(client_api, super_admin_user, entreprise_test):
    client_api.force_authenticate(user=super_admin_user)
    date_hier = (timezone.localdate() - timedelta(days=1)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": date_hier}, "motif": "Date passée refusée."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    details = rep.json()["erreur"]["details"]
    assert "date_fin" in details
    msg = str(details["date_fin"])
    assert "antérieure à aujourd'hui" in msg


@pytest.mark.django_db
def test_motif_trop_court_refuse(client_api, super_admin_user, entreprise_test):
    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()

    # Motif trop court
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}, "motif": "Court"},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    details = rep.json()["erreur"]["details"]
    assert "motif" in details
    assert "au moins 10 caractères" in str(details["motif"])

    # Motif absent
    rep2 = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep2.status_code == status.HTTP_400_BAD_REQUEST
    details2 = rep2.json()["erreur"]["details"]
    assert "motif" in details2
    assert "au moins 10 caractères" in str(details2["motif"])


@pytest.mark.django_db
def test_support_refuse(client_api, agent_support, entreprise_test):
    with schema_context(get_public_schema_name()):
        nb_journal_avant = JournalPlateforme.objects.count()

    client_api.force_authenticate(user=agent_support)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}, "motif": "Tentative support."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    with schema_context(get_public_schema_name()):
        assert JournalPlateforme.objects.count() == nb_journal_avant


@pytest.mark.django_db
def test_entreprise_suspendue_reste_suspendue(client_api, super_admin_user, entreprise_test):
    with schema_context(get_public_schema_name()):
        entreprise_test.statut = StatutEntreprise.SUSPENDU
        entreprise_test.save()
        abt = entreprise_test.abonnements.first()
        abt.statut = Abonnement.Statut.SUSPENDU
        abt.save()

    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}, "motif": "Prolongation d'un suspendu."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["statut"] == "SUSPENDU"
    with schema_context(get_public_schema_name()):
        abt.refresh_from_db()
        assert abt.statut == Abonnement.Statut.SUSPENDU


@pytest.mark.django_db
def test_abonnement_resilie_refuse(client_api, super_admin_user, entreprise_test):
    with schema_context(get_public_schema_name()):
        abt = entreprise_test.abonnements.first()
        abt.statut = Abonnement.Statut.RESILIE
        abt.save()

    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": nouvelle_date}, "motif": "Prolongation résilié."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_409_CONFLICT
    assert "résilié" in rep.json()["erreur"]["message"]


@pytest.mark.django_db
def test_meme_date_sans_trace(client_api, super_admin_user, entreprise_test):
    with schema_context(get_public_schema_name()):
        date_actuelle = entreprise_test.abonnements.first().date_fin.isoformat()
        nb_journal_avant = JournalPlateforme.objects.count()

    client_api.force_authenticate(user=super_admin_user)
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {"abonnement": {"date_fin": date_actuelle}, "motif": "Même date inchangée."},
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK
    with schema_context(get_public_schema_name()):
        assert JournalPlateforme.objects.count() == nb_journal_avant


@pytest.mark.django_db
def test_fin_essai_envoyee_par_le_client_ignoree(client_api, super_admin_user, entreprise_test):
    client_api.force_authenticate(user=super_admin_user)
    nouvelle_date = (timezone.localdate() + timedelta(days=400)).isoformat()
    rep = client_api.patch(
        f"/api/v1/admins/clients/{entreprise_test.id}/",
        {
            "abonnement": {
                "date_fin": nouvelle_date,
                "fin_essai": (timezone.localdate() + timedelta(days=50)).isoformat(),
            },
            "motif": "Date de fin sans essai.",
        },
        format="json",
        HTTP_HOST=HOTE_PLATEFORME,
    )
    assert rep.status_code == status.HTTP_200_OK
    with schema_context(get_public_schema_name()):
        abt = entreprise_test.abonnements.first()
        assert abt.fin_essai is None
