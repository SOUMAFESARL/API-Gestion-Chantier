"""La commande de démonstration — et les deux défauts qu'elle portait.

Elle n'a jamais frappé personne : c'est une commande de développement. Le
service d'inscription qui s'écrira en DEV-8 fera les mêmes gestes, en
production, sur un vrai client.
"""

import pytest
from django.core.management import call_command
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
EMAIL = "admin@demo.ci"


@pytest.fixture
def commande_jouee(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email__in=[EMAIL, "dev@demo.ci"]).delete()
    call_command("creer_tenant_demo", verbosity=0)


@pytest.mark.django_db
def test_l_administrateur_n_est_pas_un_superutilisateur(commande_jouee):
    """**R-64.** `AD` est un rôle métier, pas un statut technique.

    `is_superuser = True` court-circuite *toute* vérification de permission
    Django : la matrice de T-029 deviendrait décorative, et le client
    obtiendrait un accès inconditionnel à ses propres tables, RBAC compris.
    """
    with schema_context(SCHEMA):
        administrateur = Utilisateur.objects.get(email=EMAIL)

        # `DG` depuis T-S1-01 : le premier inscrit d'un tenant est Directeur
        # Général, pas un administrateur délégué. La démonstration suit le vrai
        # parcours d'inscription — sans quoi elle ne démontre pas ce parcours.
        assert administrateur.role_global == RoleGlobal.DIRECTEUR_GENERAL
        assert administrateur.statut == StatutUtilisateur.ACTIF
        assert administrateur.is_superuser is False
        assert administrateur.is_staff is False


@pytest.mark.django_db
def test_l_administrateur_de_demonstration_est_le_fondateur(commande_jouee):
    """La démonstration doit se comporter comme un vrai premier inscrit.

    *Sans le statut de propriétaire, l'immuabilité du fondateur — la règle qui
    empêche une entreprise de se retrouver sans personne pour gérer ses comptes
    — ne s'observait pas sur le seul tenant où l'on essaie les choses.*
    """
    from django.core.exceptions import ValidationError

    with schema_context(SCHEMA):
        administrateur = Utilisateur.objects.get(email=EMAIL)
        assert administrateur.is_owner is True
        assert administrateur.is_dg is True

        # Et la protection s'observe : c'est tout l'objet de la correction.
        administrateur.statut = StatutUtilisateur.DESACTIVE
        with pytest.raises(ValidationError, match="ne peut pas être désactivé"):
            administrateur.save()


@pytest.mark.django_db
def test_la_commande_promeut_un_administrateur_deja_cree(commande_jouee):
    """**Elle converge, elle ne se contente pas de ne rien casser.**

    Même doctrine que la réparation de `is_superuser` : sans cela, la correction
    ne vaudrait que pour les bases neuves, et les démonstrations existantes
    garderaient un administrateur que rien ne protège.
    """
    with schema_context(SCHEMA):
        administrateur = Utilisateur.objects.get(email=EMAIL)
        # On remet la démonstration dans son ancien état.
        Utilisateur.tous_objets.filter(pk=administrateur.pk).update(
            role_global=RoleGlobal.ADMIN, is_owner=False
        )

    call_command("creer_tenant_demo", verbosity=0)

    with schema_context(SCHEMA):
        administrateur = Utilisateur.objects.get(email=EMAIL)
        assert administrateur.role_global == RoleGlobal.DIRECTEUR_GENERAL
        assert administrateur.is_owner is True


@pytest.mark.django_db
def test_le_compte_technique_n_est_pas_cree_par_defaut(commande_jouee):
    """L'accès à l'admin Django ne s'obtient qu'en le demandant."""
    with schema_context(SCHEMA):
        assert not Utilisateur.objects.filter(email="dev@demo.ci").exists()


@pytest.mark.django_db
def test_le_compte_technique_est_distinct_de_l_administrateur(db):
    """L'admin Django est l'outil de l'éditeur, pas celui du client.

    Les confondre — ce que faisait `create_superuser` — donnait au client un
    accès inconditionnel à ses propres tables.
    """
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email__in=[EMAIL, "dev@demo.ci"]).delete()

    call_command("creer_tenant_demo", "--acces-django", verbosity=0)

    with schema_context(SCHEMA):
        assert Utilisateur.objects.get(email=EMAIL).is_superuser is False
        assert Utilisateur.objects.get(email="dev@demo.ci").is_superuser is True


@pytest.mark.django_db
def test_la_commande_est_idempotente(commande_jouee):
    """Relancer ne crée pas un second administrateur."""
    call_command("creer_tenant_demo", verbosity=0)

    with schema_context(SCHEMA):
        assert Utilisateur.objects.filter(email=EMAIL).count() == 1


@pytest.mark.django_db
def test_la_commande_repare_un_administrateur_deja_privilegie(commande_jouee):
    """**R-64.** Une commande idempotente converge vers l'état spécifié.

    Sans cela, la correction ne vaudrait que pour les installations neuves :
    les bases de développement existantes garderaient un `is_superuser` que
    plus personne ne penserait à retirer.
    """
    with schema_context(SCHEMA):
        administrateur = Utilisateur.objects.get(email=EMAIL)
        administrateur.is_staff = True
        administrateur.is_superuser = True
        administrateur.save(update_fields=["is_staff", "is_superuser"])

    call_command("creer_tenant_demo", verbosity=0)

    with schema_context(SCHEMA):
        administrateur.refresh_from_db()
        assert administrateur.is_superuser is False
        assert administrateur.is_staff is False


@pytest.mark.django_db
def test_la_reparation_epargne_le_compte_technique(db):
    """Le compte d'accès Django garde ses privilèges — c'est sa raison d'être."""
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email__in=[EMAIL, "dev@demo.ci"]).delete()

    call_command("creer_tenant_demo", "--acces-django", verbosity=0)
    call_command("creer_tenant_demo", verbosity=0)

    with schema_context(SCHEMA):
        assert Utilisateur.objects.get(email="dev@demo.ci").is_superuser is True
