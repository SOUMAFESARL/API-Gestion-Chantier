"""Commande `debloquer_compte` — l'outil du support.

Elle sera utilisée un jour où quelqu'un est dehors et attend. Ces tests
vérifient qu'elle fait ce qu'elle annonce, et surtout qu'elle **ne fait pas**
ce qu'elle n'annonce pas : réactiver un compte désactivé par un administrateur.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
EMAIL = "bloque@btp.ci"


@pytest.fixture
def compte_bloque(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email=EMAIL).delete()
        utilisateur = Utilisateur.objects.create_user(
            email=EMAIL,
            password="MotDePasse1!",
            nom="Traoré",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )
        utilisateur.tentatives_echouees = 5
        utilisateur.bloque_le = timezone.now()
        utilisateur.save(update_fields=["tentatives_echouees", "bloque_le"])
        yield utilisateur


def executer(*args) -> str:
    sortie = StringIO()
    call_command("debloquer_compte", *args, stdout=sortie)
    return sortie.getvalue()


@pytest.mark.django_db
def test_debloque(compte_bloque):
    sortie = executer(EMAIL, "--schema", SCHEMA)

    assert "Débloqué" in sortie
    with schema_context(SCHEMA):
        compte_bloque.refresh_from_db()
        assert not compte_bloque.est_bloque
        assert compte_bloque.tentatives_echouees == 0


@pytest.mark.django_db
def test_simulation_ne_modifie_rien(compte_bloque):
    sortie = executer(EMAIL, "--schema", SCHEMA, "--simulation")

    assert "Simulation" in sortie
    with schema_context(SCHEMA):
        compte_bloque.refresh_from_db()
        assert compte_bloque.est_bloque
        assert compte_bloque.tentatives_echouees == 5


@pytest.mark.django_db
def test_recherche_dans_tous_les_schemas_si_non_precise(compte_bloque):
    sortie = executer(EMAIL)

    assert SCHEMA in sortie
    with schema_context(SCHEMA):
        compte_bloque.refresh_from_db()
        assert not compte_bloque.est_bloque


@pytest.mark.django_db
def test_email_insensible_a_la_casse(compte_bloque):
    executer(EMAIL.upper(), "--schema", SCHEMA)

    with schema_context(SCHEMA):
        compte_bloque.refresh_from_db()
        assert not compte_bloque.est_bloque


@pytest.mark.django_db
def test_compte_deja_utilisable(compte_bloque):
    executer(EMAIL, "--schema", SCHEMA)
    sortie = executer(EMAIL, "--schema", SCHEMA)

    assert "Rien" in sortie


@pytest.mark.django_db
def test_ne_reactive_pas_un_compte_desactive(compte_bloque):
    """Blocage et désactivation ont deux sorties différentes.

    Débloquer un compte que l'administrateur a désactivé le remettrait en
    service à son insu — exactement ce que le workflow T5 interdit.
    """
    with schema_context(SCHEMA):
        compte_bloque.statut = StatutUtilisateur.DESACTIVE
        compte_bloque.save(update_fields=["statut"])

    sortie = executer(EMAIL, "--schema", SCHEMA)

    assert "pas bloqué" in sortie
    assert "n'y touche pas" in sortie
    with schema_context(SCHEMA):
        compte_bloque.refresh_from_db()
        assert compte_bloque.est_bloque  # toujours bloqué : rien n'a été touché


@pytest.mark.django_db
def test_compte_inconnu(db):
    with pytest.raises(CommandError, match="Aucun compte"):
        executer("personne@nulle-part.ci", "--schema", SCHEMA)
