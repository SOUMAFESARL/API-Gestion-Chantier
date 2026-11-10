"""Isolation des gestionnaires Django de chaque modele et absence de RLS residuelle."""

from __future__ import annotations

import pytest
from django.apps import apps
from django.db import connection

from apps.core.contexte import (
    HorsContexteEntreprise,
    contexte_entreprise,
    portee_plateforme,
    reinitialiser_contexte,
)
from apps.core.models import ModeleEntreprise
from apps.core.rls import diagnostic_isolation

pytestmark = pytest.mark.django_db

MODELES = sorted(
    (m for m in apps.get_models() if issubclass(m, ModeleEntreprise) and m._meta.managed),
    key=lambda m: m._meta.label,
)


@pytest.fixture(autouse=True)
def contexte_vierge():
    reinitialiser_contexte()
    yield
    reinitialiser_contexte()


def compter(requete: str, params=None) -> int:
    with connection.cursor() as curseur:
        curseur.execute(requete, params or [])
        return curseur.fetchone()[0]


def test_la_rls_est_retiree():
    assert diagnostic_isolation(connection) == []


@pytest.mark.parametrize("modele", MODELES, ids=lambda m: m._meta.label)
def test_hors_contexte_l_orm_refuse(modele, monde):
    for nom in ("objects", "tous_objets"):
        gestionnaire = getattr(modele, nom, None)
        if gestionnaire is None:
            continue
        with pytest.raises(HorsContexteEntreprise):
            gestionnaire.count()
        with pytest.raises(HorsContexteEntreprise):
            list(gestionnaire.all()[:1])


@pytest.mark.parametrize("modele", MODELES, ids=lambda m: m._meta.label)
def test_dans_a_l_orm_ne_voit_aucune_ligne_de_b(modele, monde):
    with contexte_entreprise(monde.a):
        for nom in ("objects", "tous_objets"):
            gestionnaire = getattr(modele, nom, None)
            if gestionnaire is not None:
                assert not gestionnaire.exclude(entreprise_id=monde.a.pk).exists()


def test_les_deux_entreprises_ont_des_donnees(monde):
    """Sans données des deux côtés, les tests ci-dessus ne prouvent rien."""
    with portee_plateforme(motif="suite d'étanchéité : volume des jeux"):
        for entreprise in (monde.a, monde.b):
            assert compter("SELECT count(*) FROM projet WHERE entreprise_id = %s", [entreprise.pk])
            assert compter("SELECT count(*) FROM element WHERE entreprise_id = %s", [entreprise.pk])
