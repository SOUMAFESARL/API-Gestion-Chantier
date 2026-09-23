"""Seuils, isolation, destinataires et reprise des rappels d'expiration."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Plan, RappelExpiration
from apps.billing.services.expiration import envoyer_rappels_expiration
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.tenants.models import Entreprise

pytestmark = pytest.mark.django_db
URL = "/api/v1/abonnement/notifications/"


@pytest.fixture
def contexte(db, settings):
    settings.FRONTEND_URL = "https://app.exemple.test"
    with schema_context("public"):
        entreprise = Entreprise.objects.get(schema_name="demo")
        plan, _ = Plan.objects.get_or_create(code=Plan.Code.PRO, defaults={"libelle": "Pro"})
        Abonnement.objects.filter(entreprise=entreprise).delete()
        abonnement = Abonnement.objects.create(
            entreprise=entreprise,
            plan=plan,
            statut=Abonnement.Statut.ACTIF,
            date_debut=timezone.localdate() - timedelta(days=30),
            date_fin=timezone.localdate() + timedelta(days=3),
        )
    with schema_context("demo"):
        admin = Utilisateur.objects.create_user(
            email="rappel.expiration@demo.ci",
            password="MotDePasse1!",
            nom="Test",
            prenom="Admin",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(admin)
    return client, abonnement, admin


@pytest.mark.parametrize(
    "jours,seuil", [(8, None), (7, 7), (6, 7), (3, 3), (2, 3), (1, 1), (0, 0), (-1, 0)]
)
def test_seuils_et_aucun_envoi_par_get(contexte, jours, seuil):
    client, abonnement, _ = contexte
    abonnement.date_fin = timezone.localdate() + timedelta(days=jours)
    with schema_context("public"):
        abonnement.save(update_fields=["date_fin"])
    response = client.get(URL)
    assert response.status_code == 200
    if seuil is None:
        assert response.json() == []
    else:
        alerte = response.json()[0]
        assert alerte["seuil"] == seuil
        assert alerte["jours_restants"] == max(0, jours)
        assert alerte["entreprise_id"] == str(abonnement.entreprise_id)
        assert alerte["lien_renouvellement"].startswith("https://app.exemple.test/")
    assert len(mail.outbox) == 0


@pytest.mark.parametrize("seuil", [7, 3, 1, 0])
def test_email_sans_doublon(contexte, seuil):
    _, abonnement, admin = contexte
    with schema_context("public"):
        abonnement.date_fin = timezone.localdate() + timedelta(days=seuil)
        abonnement.save(update_fields=["date_fin"])
    assert envoyer_rappels_expiration() == 1
    assert envoyer_rappels_expiration() == 0
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [admin.email]
    assert "https://app.exemple.test/parametres/abonnement" in mail.outbox[0].body
    assert mail.outbox[0].alternatives


def test_echec_email_reessayable(contexte):
    with patch("apps.billing.services.expiration.envoyer", return_value=False):
        assert envoyer_rappels_expiration() == 0
    with schema_context("public"):
        assert RappelExpiration.objects.filter(envoye_le__isnull=True).count() == 1
    assert envoyer_rappels_expiration() == 1


def test_renouvellement_retire_alerte_et_nouveau_cycle(contexte):
    client, abonnement, _ = contexte
    assert envoyer_rappels_expiration() == 1
    ancienne = client.get(URL).json()[0]["id"]
    with schema_context("public"):
        abonnement.date_fin += timedelta(days=30)
        abonnement.save(update_fields=["date_fin"])
    assert client.get(URL).json() == []
    assert envoyer_rappels_expiration() == 0
    with patch(
        "apps.billing.services.expiration.timezone.localdate",
        return_value=timezone.localdate() + timedelta(days=30),
    ):
        assert envoyer_rappels_expiration() == 1
        assert client.get(URL).json()[0]["id"] != ancienne


def test_acces_et_isolation(contexte):
    client, abonnement, admin = contexte
    client.force_authenticate(None)
    assert client.get(URL).status_code == 401
    admin.role_global = RoleGlobal.CHEF_PROJET
    client.force_authenticate(admin)
    assert client.get(URL).status_code == 403
    admin.role_global = RoleGlobal.ADMIN
    public = APIClient(headers={"host": "localhost"})
    public.force_authenticate(admin)
    assert public.get(URL).status_code == 403
    with schema_context("public"):
        abonnement.entreprise = Entreprise.objects.get(schema_name="public")
        abonnement.save(update_fields=["entreprise"])
    assert client.get(URL).json() == []
    assert envoyer_rappels_expiration() == 0


@pytest.mark.parametrize("statut", [Abonnement.Statut.ESSAI, Abonnement.Statut.RESILIE])
def test_pas_de_rappel_essai_ou_resilie(contexte, statut):
    client, abonnement, _ = contexte
    with schema_context("public"):
        abonnement.statut = statut
        abonnement.save(update_fields=["statut"])
    assert client.get(URL).json() == []
    assert envoyer_rappels_expiration() == 0


def test_uniquement_responsables_actifs(contexte):
    with schema_context("demo"):
        for i, (role, actif) in enumerate(
            [
                (RoleGlobal.DIRECTEUR_GENERAL, True),
                (RoleGlobal.DIRECTEUR_FINANCIER, True),
                (RoleGlobal.CHEF_PROJET, True),
                (RoleGlobal.ADMIN, False),
            ]
        ):
            Utilisateur.objects.create_user(
                email=f"rappel-{i}@demo.ci",
                password="MotDePasse1!",
                nom="Test",
                prenom="Equipe",
                role_global=role,
                is_active=actif,
                statut=StatutUtilisateur.ACTIF,
            )
    assert envoyer_rappels_expiration() == 3
    assert {m.to[0] for m in mail.outbox} == {
        "rappel.expiration@demo.ci",
        "rappel-0@demo.ci",
        "rappel-1@demo.ci",
    }
