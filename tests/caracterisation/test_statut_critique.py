"""Test de caractérisation : comportement d'un projet CRITIQUE.

Conformité SFD F3 §7 face à l'évaluation quotidienne.
[E-09 / SFD §7] Vérifie le comportement de `executer_evaluation_quotidienne_schema`
sur un projet au statut CRITIQUE.
Règle de retour SFD §7 : un projet CRITIQUE qui ne l'est plus repasse obligatoirement
par EN_RETARD (jamais directement EN_COURS).
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
    """Vérifie que executer_evaluation_quotidienne_schema fait repasser un projet
    CRITIQUE par EN_RETARD selon la SFD §7.
    """
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

    # Règle de retour SFD §7 : un projet CRITIQUE rétabli passe par EN_RETARD
    # (jamais directement EN_COURS).
    assert projet.statut != StatutProjet.CRITIQUE
    assert projet.statut == StatutProjet.EN_RETARD
