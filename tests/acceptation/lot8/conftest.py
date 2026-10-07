"""Fixture du lot 8. ADAPTABLE par Gemini (jamais les test_*.py)."""
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[2]  # .../tests
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import pytest
from django.core import mail
from django_tenants.utils import schema_context

from fabriques_lot8 import FabriqueLot8


@pytest.fixture(autouse=True)
def _positionner_schema_tenant(db):
    """Maintient la connexion sur le schéma tenant demo pendant tout le test."""
    mail.outbox.clear()
    with schema_context("public"):
        from datetime import timedelta
        from django.utils import timezone
        from apps.billing.models import Abonnement, Plan
        from apps.tenants.models import Entreprise

        entreprise = Entreprise.objects.filter(schema_name="demo").first()
        if entreprise:
            plan, _ = Plan.objects.get_or_create(
                code=Plan.Code.MAITRE_OEUVRE,
                defaults={
                    "libelle": "Plan Maître d'Œuvre Test",
                    "prix_mensuel_montant": 5000000,
                    "limite_utilisateurs": None,
                    "limite_projets": None,
                },
            )
            plan.limite_utilisateurs = None
            plan.limite_projets = None
            plan.save(update_fields=["limite_utilisateurs", "limite_projets"])

            abo = Abonnement.objects.filter(entreprise=entreprise).first()
            if not abo:
                Abonnement.objects.create(
                    entreprise=entreprise,
                    plan=plan,
                    date_debut=timezone.localdate() - timedelta(days=5),
                    date_fin=timezone.localdate() + timedelta(days=30),
                    fin_essai=timezone.localdate() + timedelta(days=30),
                    statut=Abonnement.Statut.ACTIF,
                    renouvellement_auto=True,
                )
            else:
                abo.plan = plan
                abo.statut = Abonnement.Statut.ACTIF
                abo.lecture_seule_depuis = None
                abo.fin_essai = timezone.localdate() + timedelta(days=30)
                abo.save(update_fields=["plan", "statut", "lecture_seule_depuis", "fin_essai"])

    with schema_context("demo"):
        yield
    mail.outbox.clear()


@pytest.fixture
def fabrique(db):
    """Une fabrique par test, dans un tenant de test isolé."""
    return FabriqueLot8()
