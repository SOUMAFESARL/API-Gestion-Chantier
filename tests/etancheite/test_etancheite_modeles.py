"""Couches 1 et 2 de l'isolation, éprouvées sur **chaque** modèle et **chaque** table (D9, §4.3).

Les tests unitaires de `apps/core/tests` vérifient le mécanisme sur une table ; ceux-ci vérifient
qu'aucun modèle ni aucune table n'y échappe, avec les deux entreprises peuplées :

- hors contexte, toute requête ORM sur un modèle d'entreprise lève `HorsContexteEntreprise` —
  par `objects` comme par `tous_objets` ;
- hors contexte, le SQL brut ne voit aucune ligne d'entreprise ;
- dans le contexte de A, le SQL brut ne voit aucune ligne de B ;
- le rôle de connexion subit la RLS (ni superutilisateur, ni `BYPASSRLS`).
"""

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
from apps.core.rls import TABLES_A_ENTREPRISE_NULLABLE, diagnostic_isolation

pytestmark = pytest.mark.django_db

MODELES = sorted(
    (m for m in apps.get_models() if issubclass(m, ModeleEntreprise) and m._meta.managed),
    key=lambda m: m._meta.label,
)
TABLES = sorted({m._meta.db_table for m in MODELES} | TABLES_A_ENTREPRISE_NULLABLE)


@pytest.fixture(autouse=True)
def contexte_vierge():
    reinitialiser_contexte()
    yield
    reinitialiser_contexte()


def compter(requete: str, params=None) -> int:
    with connection.cursor() as curseur:
        curseur.execute(requete, params or [])
        return curseur.fetchone()[0]


def test_le_role_de_connexion_subit_la_rls():
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


@pytest.mark.parametrize("table", TABLES)
def test_hors_contexte_le_sql_brut_ne_voit_aucune_ligne_d_entreprise(table, monde):
    requete = f'SELECT count(*) FROM "{table}" WHERE entreprise_id IS NOT NULL'
    assert compter(requete) == 0


@pytest.mark.parametrize("table", TABLES)
def test_dans_a_le_sql_brut_ne_voit_aucune_ligne_de_b(table, monde):
    with portee_plateforme(motif="suite d'étanchéité : lignes de B présentes"):
        chez_b = compter(f'SELECT count(*) FROM "{table}" WHERE entreprise_id = %s', [monde.b.pk])
    with contexte_entreprise(monde.a):
        vues = compter(
            f'SELECT count(*) FROM "{table}" WHERE entreprise_id IS DISTINCT FROM %s',
            [monde.a.pk],
        )
    assert vues == 0, (
        f"{table} : A voit {vues} lignes qui ne sont pas les siennes ({chez_b} chez B)"
    )


def test_les_deux_entreprises_ont_des_donnees(monde):
    """Sans données des deux côtés, les tests ci-dessus ne prouvent rien."""
    with portee_plateforme(motif="suite d'étanchéité : volume des jeux"):
        for entreprise in (monde.a, monde.b):
            assert compter("SELECT count(*) FROM projet WHERE entreprise_id = %s", [entreprise.pk])
            assert compter("SELECT count(*) FROM element WHERE entreprise_id = %s", [entreprise.pk])
