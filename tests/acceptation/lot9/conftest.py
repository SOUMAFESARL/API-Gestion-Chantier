"""Fixture du lot 9 (propagation super admin, plateforme)."""
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[2]  # .../tests
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import pytest
from django.core import mail
from django_tenants.utils import schema_context

from fabriques_lot9 import fabrique_lot9, FabriqueLot9


@pytest.fixture(autouse=True)
def _autoriser_ip_plateforme(settings):
    """Autorise localhost dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1", "localhost"]
    mail.outbox.clear()


@pytest.fixture(autouse=True)
def _initialiser_utilisateurs_entreprises(db):
    """Garantit qu'au moins un DG existe dans demo et dans tenant_b."""
    ea = fabrique_lot9.entreprise_a()
    eb = fabrique_lot9.entreprise_b()

    with schema_context(ea.schema_name):
        from apps.accounts.models import Utilisateur
        from apps.core.enums import RoleGlobal, StatutUtilisateur
        if not Utilisateur.objects.filter(role_global=RoleGlobal.DIRECTEUR_GENERAL, supprime_le__isnull=True).exists():
            Utilisateur.objects.create_user(
                email="dg@demo.ci",
                password="Password123!",
                nom="Directeur",
                prenom="General",
                role_global=RoleGlobal.DIRECTEUR_GENERAL,
                statut=StatutUtilisateur.ACTIF,
                is_owner=True,
            )

    with schema_context(eb.schema_name):
        from apps.accounts.models import Utilisateur
        from apps.core.enums import RoleGlobal, StatutUtilisateur
        if not Utilisateur.objects.filter(role_global=RoleGlobal.DIRECTEUR_GENERAL, supprime_le__isnull=True).exists():
            Utilisateur.objects.create_user(
                email="dg@tenant-b.ci",
                password="Password123!",
                nom="Directeur",
                prenom="General B",
                role_global=RoleGlobal.DIRECTEUR_GENERAL,
                statut=StatutUtilisateur.ACTIF,
                is_owner=True,
            )


@pytest.fixture
def fab():
    """Instance de la fabrique du lot 9."""
    return fabrique_lot9
