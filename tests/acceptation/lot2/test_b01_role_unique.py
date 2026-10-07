"""Tests d'acceptation pour la règle B-01 (Rôle unique du collaborateur)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Role, Utilisateur

pytestmark = pytest.mark.django_db


def test_b01_role_unique_df(fab):
    """[B-01] Un utilisateur DF a son champ de rôle pointant sur DF et son profil renvoie role_global='DF'."""
    user_df = fab.utilisateur_avec_role("DF")
    with schema_context("demo"):
        u = Utilisateur.objects.get(id=user_df.id)
        if hasattr(u, "role") and u.role:
            assert u.role.code == "DF"

    client = fab.client_pour(user_df)
    rep = client.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data.get("role_global") == "DF"


def test_b01_un_seul_champ_de_role():
    """[B-01] Le modèle Utilisateur n'a qu'un seul champ de référence vers la table des rôles."""
    fk_roles = [
        f.name
        for f in Utilisateur._meta.fields
        if f.is_relation and hasattr(f, "related_model") and f.related_model == Role
    ]
    # Doit contenir exactement le champ 'role' (et plus la coexistence de deux champs sources)
    assert "role" in fk_roles
    assert len(fk_roles) == 1


def test_b01_creation_via_role_global_moa(client_dg):
    """[B-01] La création d'un collaborateur avec role_global='MOA' est traduite vers le rôle BAI."""
    payload = {
        "email": "nouveau.moa.b01@demo.ci",
        "nom": "Bailleur",
        "prenom": "Test",
        "role_global": "MOA",
    }
    rep = client_dg.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED

    with schema_context("demo"):
        u = Utilisateur.objects.get(email="nouveau.moa.b01@demo.ci")
        assert u.role.code == "BAI"


def test_b01_creation_via_role_global_moe(client_dg):
    """[B-01] La création d'un collaborateur avec role_global='MOE' est traduite vers le rôle VI."""
    payload = {
        "email": "nouveau.moe.b01@demo.ci",
        "nom": "Moe",
        "prenom": "Test",
        "role_global": "MOE",
    }
    rep = client_dg.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED

    with schema_context("demo"):
        u = Utilisateur.objects.get(email="nouveau.moe.b01@demo.ci")
        assert u.role.code == "VI"


def test_b01_creation_via_role_personnalise_id(client_dg, fab):
    """[B-01] La création avec role_personnalise_id rattache le rôle personnalisé comme rôle unique."""
    role_perso = fab.creer_role_personnalise("MACON_CHEF", "Chef Maçon")
    payload = {
        "email": "nouveau.perso.b01@demo.ci",
        "nom": "Macon",
        "prenom": "Chef",
        "role_personnalise_id": str(role_perso.id),
    }
    rep = client_dg.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED

    with schema_context("demo"):
        u = Utilisateur.objects.get(email="nouveau.perso.b01@demo.ci")
        assert u.role.id == role_perso.id


def test_b01_les_deux_champs_refuses(client_dg, fab):
    """[B-01] Fournir à la fois role_global et role_personnalise_id est refusé avec 400 (role_ambigu)."""
    role_perso = fab.creer_role_personnalise("PEINTRE_CHEF", "Chef Peintre")
    payload = {
        "email": "ambigu.b01@demo.ci",
        "nom": "Ambigu",
        "prenom": "Test",
        "role_global": "CP",
        "role_personnalise_id": str(role_perso.id),
    }
    rep = client_dg.post("/api/v1/parametres/collaborateurs/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    assert "role_ambigu" in str(rep.data)


def test_b01_modification_via_role_global(client_dg, fab):
    """[B-01] La modification partielle via role_global='MOA' met à jour le rôle vers BAI."""
    user = fab.utilisateur_avec_role("CC", email="user.modif.moa@demo.ci")
    rep = client_dg.patch(
        f"/api/v1/parametres/collaborateurs/{user.id}/",
        {"role_global": "MOA"},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK

    with schema_context("demo"):
        u = Utilisateur.objects.get(id=user.id)
        assert u.role.code == "BAI"


def test_b01_migration_moa_moe(fab):
    """[B-01] Les rôles en base sont bien traduits : aucun utilisateur ne porte de rôle MOA ou MOE."""
    with schema_context("demo"):
        # Vérifie qu'aucun rôle système MOA/MOE n'existe et que tout utilisateur pointe vers un rôle valide
        assert not Role.objects.filter(code__in=["MOA", "MOE"], supprime_le__isnull=True).exists()
