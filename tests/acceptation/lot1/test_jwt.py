"""Tests d'acceptation du jeton JWT (Règle B-11)."""

import jwt
import pytest
from django.conf import settings
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.catalogue.models import CatalogueModule, CataloguePermission
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_TEST = "demo"
HOTE_TENANT = "demo.localhost"

pytestmark = pytest.mark.django_db


def test_b11_jwt_sans_permission(client_tenant):
    """[B-11] Le jeton d'accès JWT ne transporte aucune liste de permissions ni d'habilitations."""
    with schema_context(SCHEMA_TEST):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="user.jwt.test@demo.ci",
            defaults={
                "nom": "JWT",
                "prenom": "Test",
                "role_global": RoleGlobal.CONDUCTEUR_TRAVAUX,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user.set_password("Password123!")
        user.save()

    rep = client_tenant.post(
        "/api/v1/auth/token/",
        {"email": "user.jwt.test@demo.ci", "mot_de_passe": "Password123!"},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK
    token_str = rep.data["access"]
    payload = jwt.decode(token_str, options={"verify_signature": False})

    assert "permissions" not in payload, "Le JWT ne doit pas contenir la clé 'permissions'"
    assert "habilitations" not in payload, "Le JWT ne doit pas contenir la clé 'habilitations'"


def test_b11_claim_role_global_ignore_pour_acces(client_tenant):
    """[B-11] Un claim 'role_global' falsifié dans le JWT ne permet pas de contourner les droits en base."""
    with schema_context(SCHEMA_TEST):
        user_vi, _ = Utilisateur.tous_objets.get_or_create(
            email="visiteur.hacker@demo.ci",
            defaults={
                "nom": "Visiteur",
                "prenom": "Hacker",
                "role_global": RoleGlobal.VISITEUR,
                "statut": StatutUtilisateur.ACTIF,
            },
        )

    # Forger un jeton valide signé avec un faux claim role_global = DG
    token = AccessToken.for_user(user_vi)
    token["schema"] = SCHEMA_TEST
    token["role_global"] = "DG"  # tentative d'élévation frauduleuse dans le claim
    token_str = str(token)

    client_tenant.credentials(HTTP_AUTHORIZATION=f"Bearer {token_str}")
    # Tentative d'accès à une action réservée à l'administration
    rep = client_tenant.get("/api/v1/roles/")
    # Le serveur doit vérifier le statut réel en base et refuser
    assert rep.status_code == status.HTTP_403_FORBIDDEN


def test_b11_changement_de_role_immediat(client_tenant):
    """[B-11] Un changement de rôle en base s'applique immédiatement à la requête suivante avec le même JWT."""
    with schema_context(SCHEMA_TEST):
        role_initial, _ = Role.objects.get_or_create(
            code="ROLE_DEBUT",
            defaults={"libelle": "Rôle Début", "est_systeme": False, "est_actif": True},
        )
        role_final, _ = Role.objects.get_or_create(
            code="ROLE_FIN",
            defaults={"libelle": "Rôle Fin", "est_systeme": False, "est_actif": True},
        )
        mod_tiers = CatalogueModule.objects.get(code="tiers")
        rmp, _ = RoleModulePermission.objects.get_or_create(role=role_final, module_catalogue=mod_tiers)
        p_lire = CataloguePermission.objects.filter(code="tiers.lire").first()
        if p_lire:
            rmp.permissions_catalogue.set([p_lire])

        user, _ = Utilisateur.tous_objets.get_or_create(
            email="user.role.immediat@demo.ci",
            defaults={
                "nom": "Changement",
                "prenom": "Immediat",
                "role_global": RoleGlobal.VISITEUR,
                "role_personnalise": role_initial,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user.role_personnalise = role_initial
        user.save()

    token = AccessToken.for_user(user)
    token["schema"] = SCHEMA_TEST
    client_tenant.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")

    rep1 = client_tenant.get("/api/v1/auth/profil/")
    assert "tiers.lire" not in rep1.data.get("permissions", [])

    # Changement du rôle en base
    with schema_context(SCHEMA_TEST):
        user.role_personnalise = role_final
        user.save()

    # Même token JWT, nouvelle requête
    rep2 = client_tenant.get("/api/v1/auth/profil/")
    assert "tiers.lire" in rep2.data.get("permissions", [])
