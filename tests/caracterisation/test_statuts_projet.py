"""Test de caractérisation : comportement actuel des changements de statut d'un projet.

[E-08] Caractérise le comportement actuel où un membre affecté au projet (même VISITEUR)
peut modifier le statut du projet via PATCH.
Selon la future règle E-08, cette exception sera supprimée et les permissions seront inversées.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet
from apps.projets.tests.test_creation_formulaire_strict import payload

pytestmark = pytest.mark.django_db


def test_statuts_projet_comportement_actuel_membre(schema_demo):
    """Vérifie que sur le code actuel, un membre affecté peut changer le statut en SUSPENDU."""
    admin = Utilisateur.objects.create_user(
        email="admin.statuts@demo.ci",
        password="TestPassword123!",
        nom="Admin Statuts",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    admin_client = APIClient(HTTP_HOST="demo.localhost")
    admin_client.force_authenticate(admin)
    created = admin_client.post("/api/v1/projets/", payload(), format="json")
    assert created.status_code == 201
    projet = Projet.objects.get(pk=created.data["id"])

    visiteur = Utilisateur.objects.create_user(
        email="visiteur.statuts@demo.ci",
        password="TestPassword123!",
        nom="Visiteur Test",
        role_global=RoleGlobal.VISITEUR,
        statut=StatutUtilisateur.ACTIF,
    )
    visiteur_client = APIClient(HTTP_HOST="demo.localhost")
    visiteur_client.force_authenticate(visiteur)
    url = created["Location"]

    # Sans affectation : refus 403
    assert visiteur_client.patch(url, {"statut": "SUSPENDU"}, format="json").status_code == 403

    # Avec affectation membre : refusé 403 selon E-08 (suppression de l'exception historique)
    AffectationProjet.objects.create(
        utilisateur=visiteur,
        projet=projet,
        role_projet=RoleProjet.VISITEUR,
    )
    res = visiteur_client.patch(url, {"statut": "SUSPENDU"}, format="json")
    assert res.status_code == 403
    projet.refresh_from_db()
    assert projet.statut == StatutProjet.EN_ATTENTE
