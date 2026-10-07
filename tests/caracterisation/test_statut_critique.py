"""Test de caractérisation : comportement actuel d'un projet CRITIQUE face à l'évaluation quotidienne.

[E-09] Vérifie ce que fait aujourd'hui `executer_evaluation_quotidienne_schema` sur un projet au statut CRITIQUE.
Constat : le statut CRITIQUE est ÉCRASÉ par l'évaluation calendaire (car absent de STATUTS_PROJET_MANUELS_FIXES).
"""

from datetime import timedelta
import pytest
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutProjet, StatutUtilisateur, TypeTiers
from apps.projets.models import Projet
from apps.projets.services.machine_etats import executer_evaluation_quotidienne_schema
from apps.tiers.models import Tiers


@pytest.mark.django_db
def test_evaluation_quotidienne_ecrase_statut_critique(schema_demo):
    """Vérifie que executer_evaluation_quotidienne_schema écrase actuellement le statut CRITIQUE."""
    admin = Utilisateur.objects.create_user(
        email="admin.critique@demo.ci",
        password="TestPassword123!",
        nom="Admin Critique",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    client_tiers = Tiers.objects.create(
        type_tiers=TypeTiers.ENTREPRISE,
        raison_sociale="Client Test",
        telephone="0102030405",
        cree_par=admin,
    )
    aujourdhui = timezone.now().date()
    projet = Projet.objects.create(
        nom="Projet Critique Test",
        client=client_tiers,
        cree_par=admin,
        date_debut_prevue=aujourdhui - timedelta(days=10),
        date_fin_prevue=aujourdhui + timedelta(days=20),
        statut=StatutProjet.CRITIQUE,
    )

    # Exécution de l'évaluation quotidienne calendaire sur le schéma
    executer_evaluation_quotidienne_schema(date_reference=aujourdhui)

    # Rechargement depuis la base
    projet.refresh_from_db()

    # Constat : le statut CRITIQUE a été écrasé (il passe à EN_COURS selon les dates calendaires)
    assert projet.statut != StatutProjet.CRITIQUE
    assert projet.statut == StatutProjet.EN_COURS
