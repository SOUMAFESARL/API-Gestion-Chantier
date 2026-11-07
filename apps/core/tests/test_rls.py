"""Deuxième couche de l'isolation : PostgreSQL filtre de lui-même (D9, lot 4, règle R-5).

Ces tests passent **sous** la première couche : ils interrogent la base en SQL brut, là où le
gestionnaire cloisonné ne voit rien. C'est le cas que la RLS doit couvrir — un `cursor.execute`,
un `_base_manager`, un filtre oublié.
"""

import uuid

import pytest
from django.db import connection, transaction

from apps.core.contexte import contexte_entreprise, portee_plateforme, reinitialiser_contexte
from apps.core.rls import diagnostic_isolation, role_plateforme
from apps.projets.models import MotifReport
from apps.entreprises.models import Entreprise

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def contexte_vierge():
    reinitialiser_contexte()
    yield
    reinitialiser_contexte()


def creer_entreprise(slug: str) -> Entreprise:
    return Entreprise.objects.create(
        slug=slug, raison_sociale=slug.upper(), email_contact=f"contact@{slug}.test"
    )


@pytest.fixture
def deux_entreprises():
    a, b = creer_entreprise("rlsa"), creer_entreprise("rlsb")
    with contexte_entreprise(a):
        MotifReport.objects.create(code="PLUIE", libelle="Pluie")
    with contexte_entreprise(b):
        MotifReport.objects.create(code="GREVE", libelle="Grève")
        MotifReport.objects.create(code="PANNE", libelle="Panne")
    return a, b


def brut(requete: str, params=None):
    with connection.cursor() as curseur:
        curseur.execute(requete, params or [])
        return curseur.fetchall()


def codes() -> set[str]:
    return {code for (code,) in brut("SELECT code FROM motif_report")}


# --- Ce que voit le SQL brut ---------------------------------------------------------------------
def test_hors_contexte_le_sql_brut_ne_voit_rien(deux_entreprises):
    assert codes() == set()


def test_dans_une_entreprise_le_sql_brut_ne_voit_que_ses_lignes(deux_entreprises):
    a, b = deux_entreprises
    with contexte_entreprise(a):
        assert codes() == {"PLUIE"}
    with contexte_entreprise(b):
        assert codes() == {"GREVE", "PANNE"}
    assert codes() == set()


def test_le_base_manager_est_borne_lui_aussi(deux_entreprises):
    a, _ = deux_entreprises
    with contexte_entreprise(a):
        assert set(MotifReport._base_manager.values_list("code", flat=True)) == {"PLUIE"}


def test_ecrire_pour_une_autre_entreprise_est_refuse(deux_entreprises):
    a, b = deux_entreprises
    with (
        contexte_entreprise(a),
        pytest.raises(Exception, match="row-level security"),
        transaction.atomic(),
    ):
        brut(
            "INSERT INTO motif_report (id, entreprise_id, code, libelle, description, "
            "est_actif, ordre, cree_le, modifie_le) "
            "VALUES (%s, %s, 'X', 'X', '', true, 0, now(), now()) RETURNING id",
            [uuid.uuid4(), b.pk],
        )


def test_la_portee_plateforme_voit_tout(deux_entreprises):
    with portee_plateforme(motif="test de la RLS"):
        assert codes() == {"PLUIE", "GREVE", "PANNE"}
        assert brut("SELECT current_user")[0][0] == role_plateforme()
    assert brut("SELECT current_user")[0][0] != role_plateforme()
    assert codes() == set()


# --- La session reste d'accord avec le contexte ---------------------------------------------------
def test_reglage_retabli_apres_annulation_d_un_point_de_sauvegarde(deux_entreprises):
    """`ROLLBACK TO SAVEPOINT` annule le `set_config` fait depuis : la mémoire doit l'oublier."""
    a, b = deux_entreprises
    with contexte_entreprise(a):
        assert codes() == {"PLUIE"}
        try:
            with transaction.atomic(), contexte_entreprise(b):
                assert codes() == {"GREVE", "PANNE"}
                raise RuntimeError("annulation")
        except RuntimeError:
            pass
        # Côté serveur, le réglage est revenu à A par l'annulation ; côté Python aussi.
        assert codes() == {"PLUIE"}
        with contexte_entreprise(b):
            assert codes() == {"GREVE", "PANNE"}


def test_le_reglage_ne_compte_pas_comme_une_requete(deux_entreprises, django_assert_num_queries):
    a, _ = deux_entreprises
    with contexte_entreprise(a), django_assert_num_queries(1):
        list(MotifReport.objects.all())


# --- Le garde-fou ---------------------------------------------------------------------------------
def test_isolation_en_place_sur_la_base():
    """Rôle de connexion ni superutilisateur ni BYPASSRLS, rôle plateforme accordé, toutes les
    tables d'entreprise sous RLS forcée."""
    assert diagnostic_isolation(connection) == []
