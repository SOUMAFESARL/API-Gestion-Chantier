"""Fixtures globales.

Le produit est multi-schéma : un test qui touche des données métier n'a de
sens que dans un schéma de tenant. Sans les fixtures ci-dessous, le middleware
ne résout aucun tenant, retombe sur le routage public, et **toutes les routes
métier répondent 404** — une erreur qui ressemble à un problème d'URL alors
que c'est une donnée manquante.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context

SCHEMA_TEST = "demo"
HOTE_TEST = "demo.localhost"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Crée le tenant de test et son schéma, une fois pour toute la session.

    La création du schéma est du DDL : elle survit au retour arrière que
    pytest-django applique après chaque test, à condition que les tests ne
    demandent pas `transaction=True` — qui, lui, vide les tables.
    """
    with django_db_blocker.unblock():
        from apps.core.enums import StatutEntreprise
        from apps.tenants.models import Domaine, Entreprise

        with schema_context(get_public_schema_name()):
            # Le schéma public doit être adressable, comme en production.
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

            entreprise = Entreprise.objects.filter(schema_name=SCHEMA_TEST).first()
            if entreprise is None:
                entreprise = Entreprise(
                    schema_name=SCHEMA_TEST,
                    raison_sociale="Entreprise de test",
                    email_contact="test@demo.ci",
                    statut=StatutEntreprise.ESSAI,
                )
                entreprise.save(verbosity=0)

            Domaine.objects.get_or_create(
                domain=HOTE_TEST, defaults={"tenant": entreprise, "is_primary": True}
            )

    return django_db_setup


@pytest.fixture
def schema_demo():
    """Active le schéma du tenant de test pour un accès direct à l'ORM.

    Inutile pour un appel HTTP : l'en-tête `Host` suffit, c'est le middleware
    qui résout le schéma.
    """
    with schema_context(SCHEMA_TEST):
        yield SCHEMA_TEST


@pytest.fixture(autouse=True)
def cache_propre():
    """Vide le cache entre deux tests.

    Sans cela, l'état de la limitation de débit d'un test fuit dans le
    suivant, et l'échec apparaît dans un test qui n'y est pour rien.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
