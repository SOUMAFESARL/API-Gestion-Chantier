"""Tests de vérification de la journalisation d'audit des connexions et déconnexions."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "AuditPass123!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def utilisateur_audit(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="audit.user@demo.ci").delete()
        user = Utilisateur.objects.create_user(
            email="audit.user@demo.ci",
            password=MOT_DE_PASSE,
            nom="Audit",
            prenom="User",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        yield user
        Utilisateur.tous_objets.filter(pk=user.pk).delete()


@pytest.mark.django_db
def test_connexion_et_deconnexion_journalisees(client, utilisateur_audit):
    # 1. Connexion réussie
    rep_login = client.post(
        "/api/v1/auth/token/",
        {"email": utilisateur_audit.email, "mot_de_passe": MOT_DE_PASSE, "origine": "WEB"},
        format="json",
    )
    assert rep_login.status_code == status.HTTP_200_OK
    refresh_token = rep_login.data["refresh"]

    with schema_context(SCHEMA):
        entree_connexion = (
            JournalAudit.objects.filter(
                action=ActionAudit.CONNEXION,
                utilisateur_id=utilisateur_audit.pk,
            )
            .order_by("-horodatage")
            .first()
        )
        assert entree_connexion is not None
        assert entree_connexion.type_entite == "utilisateur"
        assert entree_connexion.valeur_apres == {"origine": "WEB"}

    # 2. Déconnexion
    rep_logout = client.post(
        "/api/v1/auth/deconnexion/",
        {"refresh": refresh_token},
        format="json",
    )
    assert rep_logout.status_code == status.HTTP_200_OK

    with schema_context(SCHEMA):
        entree_deconnexion = (
            JournalAudit.objects.filter(
                action=ActionAudit.DECONNEXION,
                utilisateur_id=utilisateur_audit.pk,
            )
            .order_by("-horodatage")
            .first()
        )
        assert entree_deconnexion is not None
        assert entree_deconnexion.type_entite == "utilisateur"
        assert entree_deconnexion.valeur_apres is not None
        assert "sid" in entree_deconnexion.valeur_apres
