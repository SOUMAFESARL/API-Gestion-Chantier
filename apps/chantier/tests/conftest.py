"""Fixtures multi-tenant pour les tests du journal de chantier."""

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django_tenants.utils import get_public_schema_name, schema_context

SCHEMA_TEST = "demo"
HOTE_TEST = "demo.localhost"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        from apps.core.enums import StatutEntreprise
        from apps.tenants.models import Domaine, Entreprise

        with schema_context(get_public_schema_name()):
            public, _ = Entreprise.objects.get_or_create(
                schema_name=get_public_schema_name(),
                defaults={
                    "raison_sociale": "CCD Digital",
                    "email_contact": "contact@ccd-digital.ci",
                    "statut": StatutEntreprise.ACTIF,
                },
            )
            public.auto_create_schema = False
            Domaine.objects.get_or_create(
                domain="localhost", defaults={"tenant": public, "is_primary": True}
            )
            call_command("synchroniser_catalogue_permissions")

            entreprise = Entreprise.objects.filter(schema_name=SCHEMA_TEST).first()
            if entreprise is None:
                entreprise = Entreprise(
                    schema_name=SCHEMA_TEST,
                    raison_sociale="Entreprise de test",
                    email_contact="test@demo.ci",
                    statut=StatutEntreprise.ACTIF,
                )
                entreprise.save(verbosity=0)

            Domaine.objects.get_or_create(
                domain=HOTE_TEST, defaults={"tenant": entreprise, "is_primary": True}
            )
            call_command("propager_roles_systeme")

    return django_db_setup


@pytest.fixture
def schema_demo():
    with schema_context(SCHEMA_TEST):
        yield SCHEMA_TEST


@pytest.fixture(autouse=True)
def cache_propre():
    cache.clear()
    yield
    cache.clear()
