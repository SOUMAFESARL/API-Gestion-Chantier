"""La porte du personnel de l'éditeur — matrice des rôles §1.1.

**Le Super Admin n'est pas un rôle, c'est un territoire.** Il vit dans
`public.utilisateur`, la même table que les collaborateurs d'un client mais dans
un autre schéma (écart E1). Ce qui le distingue n'est donc pas une colonne qu'on
peut se donner : c'est l'endroit d'où il se connecte.
"""

import json

import pytest
from django.test.utils import override_settings
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

TOKEN = "/api/v1/auth/token/"
MOT_DE_PASSE = "Plateforme2026!"


@pytest.fixture(autouse=True)
def cache_vide():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def personnel(db):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="essai-support@ccd-digital.ci").delete()
        yield Utilisateur.objects.create_user(
            email="essai-support@ccd-digital.ci",
            password=MOT_DE_PASSE,
            nom="Support",
            prenom="CCD",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )


@pytest.mark.django_db
def test_le_personnel_se_connecte_sur_le_domaine_plateforme(personnel):
    """La liste blanche est explicite : sous pytest, `DEBUG` vaut `False`, et
    une liste vide interdit alors tout — c'est précisément la règle."""
    client = APIClient(headers={"host": "localhost"})

    with override_settings(SUPER_ADMIN_IPS=["127.0.0.1"]):
        reponse = client.post(
            TOKEN, {"email": personnel.email, "mot_de_passe": MOT_DE_PASSE}, format="json"
        )

    assert reponse.status_code == 200
    assert "access" in reponse.data


@pytest.mark.django_db
def test_un_compte_plateforme_n_ouvre_aucun_espace_client(personnel):
    """**L'isolation, vue depuis la porte d'entrée.**

    Le compte existe dans `public`, pas dans `demo` : le même identifiant, le
    même mot de passe, et pourtant rien. C'est ce que garantit un schéma par
    client — pas un filtre qu'un développeur pense à écrire.
    """
    client = APIClient(headers={"host": "demo.localhost"})

    reponse = client.post(
        TOKEN, {"email": personnel.email, "mot_de_passe": MOT_DE_PASSE}, format="json"
    )

    assert reponse.status_code == 401


@pytest.mark.django_db
def test_une_ip_hors_liste_blanche_est_refusee(personnel):
    """Matrice §1.1 — « accès restreint par adresse IP ».

    Le refus arrive **avant** l'authentification : le mot de passe est correct,
    et la réponse est `403`. Une porte d'administration qui vérifierait d'abord
    les identifiants dirait à qui frappe que le compte existe.
    """
    client = APIClient(headers={"host": "localhost"})

    with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"]):
        reponse = client.post(
            TOKEN, {"email": personnel.email, "mot_de_passe": MOT_DE_PASSE}, format="json"
        )

    assert reponse.status_code == 403
    # Le refus vient du middleware, avant DRF : c'est un `JsonResponse`, pas
    # une `Response` — il n'a donc pas d'attribut `.data`.
    assert json.loads(reponse.content)["erreur"]["code"] == "acces_refuse"


@pytest.mark.django_db
def test_une_ip_de_la_liste_blanche_passe(personnel):
    client = APIClient(headers={"host": "localhost"})

    with override_settings(SUPER_ADMIN_IPS=["127.0.0.1"]):
        reponse = client.post(
            TOKEN, {"email": personnel.email, "mot_de_passe": MOT_DE_PASSE}, format="json"
        )

    assert reponse.status_code == 200


@pytest.mark.django_db
def test_hors_developpement_une_liste_vide_interdit_tout(personnel):
    """**La valeur par défaut d'une porte d'administration est fermée.**

    Un déploiement qui oublie `SUPER_ADMIN_IPS` s'en aperçoit à la première
    connexion — ce qui vaut infiniment mieux que de ne jamais s'en apercevoir.
    """
    client = APIClient(headers={"host": "localhost"})

    with override_settings(SUPER_ADMIN_IPS=[], DEBUG=False):
        reponse = client.post(
            TOKEN, {"email": personnel.email, "mot_de_passe": MOT_DE_PASSE}, format="json"
        )

    assert reponse.status_code == 403


@pytest.mark.django_db
def test_la_restriction_ne_touche_pas_les_clients(personnel):
    """Elle ne vaut que pour le schéma `public`.

    Un chef de chantier n'a pas d'adresse IP fixe — la lui imposer fermerait le
    produit à ceux pour qui il est fait.
    """
    from apps.core.enums import RoleGlobal as R

    with schema_context("demo"):
        Utilisateur.tous_objets.filter(email="terrain@demo.ci").delete()
        Utilisateur.objects.create_user(
            email="terrain@demo.ci",
            password=MOT_DE_PASSE,
            nom="Kouassi",
            prenom="Ange",
            role_global=R.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )

    client = APIClient(headers={"host": "demo.localhost"})
    with override_settings(SUPER_ADMIN_IPS=["10.0.0.1"], DEBUG=False):
        reponse = client.post(
            TOKEN, {"email": "terrain@demo.ci", "mot_de_passe": MOT_DE_PASSE}, format="json"
        )

    assert reponse.status_code == 200
