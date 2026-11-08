"""Fixtures des tests de l'arbre : une entreprise `demo` active pendant le test."""

import pytest
from django.core.cache import cache
from django.core.management import call_command

from apps.core.contexte import contexte_entreprise

SLUG_TEST = "demo"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        from apps.core.enums import StatutEntreprise
        from apps.entreprises.models import Entreprise

        call_command("synchroniser_catalogue_permissions")
        if not Entreprise.objects.filter(slug=SLUG_TEST).exists():
            Entreprise.objects.create(
                slug=SLUG_TEST,
                raison_sociale="Entreprise de test",
                email_contact="test@demo.ci",
                statut=StatutEntreprise.ACTIF,
            )
        call_command("propager_roles_systeme")

    return django_db_setup


@pytest.fixture
def entreprise_demo():
    from apps.entreprises.models import Entreprise

    entreprise = Entreprise.objects.get(slug=SLUG_TEST)
    with contexte_entreprise(entreprise):
        yield entreprise


@pytest.fixture(autouse=True)
def cache_propre():
    cache.clear()
    yield
    cache.clear()
