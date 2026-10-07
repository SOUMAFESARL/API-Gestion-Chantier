"""Plomberie et canaris du lot 8 (collaborateurs, registre global, abonnement, lectures).

Vérifie l'isolation, la résolution des rôles et l'opérabilité des fabriques avant tout test métier.
Tous les tests de ce fichier sont des canaris 'carac' qui doivent passer dès le départ.
"""

import pytest
from rest_framework import status

pytestmark = [pytest.mark.django_db, pytest.mark.carac]


def test_00_canari_acteurs_et_authentification(fabrique):
    """[PLOMBERIE] Chaque client API représente fidèlement son propre utilisateur."""
    for code in ("DG", "AD", "DO", "DF", "CP", "CT", "VI"):
        user = fabrique.utilisateur(code)
        client = fabrique.client(user)
        res = client.get("/api/v1/auth/profil/")
        assert res.status_code == status.HTTP_200_OK, f"Échec de lecture profil pour {code}"
        assert res.data["email"] == user.email


def test_00_canari_role_personnalise_entreprise(fabrique):
    """[PLOMBERIE] L'acteur perso_entreprise possède un rôle à portée ENTREPRISE."""
    user = fabrique.utilisateur("perso_entreprise")
    assert user.role_personnalise is not None
    assert user.role_personnalise.portee == "ENTREPRISE"
    client = fabrique.client(user)
    res = client.get("/api/v1/auth/profil/")
    assert res.status_code == status.HTTP_200_OK


def test_00_canari_urls_et_routes_lot8(fabrique):
    """[PLOMBERIE] Les URL déclarées dans la fabrique répondent au format standard."""
    assert fabrique.url_invitations() == "/api/v1/invitations/"
    assert fabrique.url_collaborateurs() == "/api/v1/parametres/collaborateurs/"
    assert fabrique.url_factures() == "/api/v1/factures/"
    assert fabrique.url_onboarding() == "/api/v1/configuration/"


def test_00_canari_enveloppe_quota_utilisateurs(fabrique):
    """[PLOMBERIE] La sonde d'enveloppe de quota collaborateurs s'exécute et retourne un 403."""
    env = fabrique.enveloppe_quota_utilisateurs()
    assert env["status_code"] == status.HTTP_403_FORBIDDEN
    assert env["code"] in ("quota_plan_atteint", "QUOTA_PLAN_ATTEINT", "quota_atteint")
