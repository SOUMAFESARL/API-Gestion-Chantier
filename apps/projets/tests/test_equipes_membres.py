"""Tests pour la gestion des équipes, membres et affectations d'activités (B5)."""

import importlib

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet
from apps.projets.models import (
    Activite,
    AffectationProjet,
    EquipeChantier,
    Lot,
    MembreEquipeChantier,
    Projet,
)

_migration_mod = importlib.import_module(
    "apps.projets.migrations.0032_migration_donnees_equipes_chef_et_nature"
)
migrer_chefs_et_nature = _migration_mod.migrer_chefs_et_nature

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexte(schema_demo):
    user_ct = Utilisateur.objects.create_user(
        email="ct.equipes@demo.ci",
        password="Test12345!",
        nom="Touré",
        prenom="Moussa",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
    )
    user_ouvrier = Utilisateur.objects.create_user(
        email="ouvrier.affecte@demo.ci",
        password="Test12345!",
        nom="Koné",
        prenom="Amara",
        role_global=RoleGlobal.CHEF_CHANTIER,
    )
    user_non_affecte = Utilisateur.objects.create_user(
        email="autre.user@demo.ci",
        password="Test12345!",
        nom="Diallo",
        prenom="Ibrahim",
        role_global=RoleGlobal.CHEF_CHANTIER,
    )
    user_visiteur = Utilisateur.objects.create_user(
        email="visiteur@demo.ci",
        password="Test12345!",
        nom="Kouassi",
        prenom="Paul",
        role_global=RoleGlobal.VISITEUR,
    )

    projet = Projet.objects.create(reference="PRJ-B5", nom="Projet B5", ville="Abidjan")
    AffectationProjet.objects.create(
        utilisateur=user_ct,
        projet=projet,
        role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
    )
    AffectationProjet.objects.create(
        utilisateur=user_ouvrier,
        projet=projet,
        role_projet=RoleProjet.CHEF_CHANTIER,
    )
    AffectationProjet.objects.create(
        utilisateur=user_visiteur,
        projet=projet,
        role_projet=RoleProjet.VISITEUR,
    )

    lot = Lot.objects.create(projet=projet, code="LOT-01", libelle="Gros Œuvre")
    activite = Activite.objects.create(lot=lot, libelle="Fondations", quantite_prevue=10)

    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user_ct)

    return {
        "client": client,
        "projet": projet,
        "lot": lot,
        "activite": activite,
        "user_ct": user_ct,
        "user_ouvrier": user_ouvrier,
        "user_non_affecte": user_non_affecte,
        "user_visiteur": user_visiteur,
    }


def test_creation_format_actuel_toujours_accepte(contexte):
    client = contexte["client"]
    projet = contexte["projet"]
    user_ouvrier = contexte["user_ouvrier"]

    url = f"/api/v1/projets/{projet.pk}/equipes/"
    corps = {
        "nom": "Équipe Coffrage",
        "nature": "INTERNE",
        "corps_etat": "Gros Œuvre",
        "chef": {"nom": "Chef Coffrage"},
        "membres": [{"utilisateur_id": str(user_ouvrier.pk), "fonction": "OUVRIER"}],
    }
    response = client.post(url, corps, format="json")
    assert response.status_code == 201, response.data
    data = response.data
    assert data["nom"] == "Équipe Coffrage"
    assert data["chef_nom"] == "Chef Coffrage"
    assert data["effectif"] == 2


def test_creation_format_ecran(contexte):
    client = contexte["client"]
    projet = contexte["projet"]
    user_ct = contexte["user_ct"]

    url = f"/api/v1/projets/{projet.pk}/equipes/"
    corps = {
        "nom": "Équipe Écran",
        "nature": "SOUS_TRAITANT",
        "specialite": "Électricité",
        "chef": {"collaborateur_id": str(user_ct.pk)},
        "membres": [
            {
                "prenom": "Jean",
                "nom": "Kouamé",
                "role": "MANOEUVRE",
            }
        ],
    }
    response = client.post(url, corps, format="json")
    assert response.status_code == 201, response.data
    data = response.data
    assert data["projet_id"] == str(projet.pk)
    assert data["specialite"] == "Électricité"
    assert data["chef"] is not None
    assert data["chef"]["collaborateur_id"] == str(user_ct.pk)
    assert data["chef"]["role"] == "CHEF_EQUIPE"
    assert len(data["membres"]) == 1
    assert data["membres"][0]["role"] == "MANOEUVRE"
    assert data["membres"][0]["nom"] == "Kouamé"
    assert data["effectif"] == 2


def test_sous_traitante_converti(contexte):
    client = contexte["client"]
    projet = contexte["projet"]

    url = f"/api/v1/projets/{projet.pk}/equipes/"
    corps = {
        "nom": "Équipe ST",
        "nature": "SOUS_TRAITANTE",
        "corps_etat": "Plomberie",
        "chef": {"nom": "Chef ST"},
    }
    response = client.post(url, corps, format="json")
    assert response.status_code == 201, response.data
    assert response.data["nature"] == "SOUS_TRAITANT"

    equipe = EquipeChantier.objects.get(pk=response.data["id"])
    assert equipe.nature == "SOUS_TRAITANT"


def test_migration_chef_devient_membre(contexte):
    projet = contexte["projet"]
    equipe = EquipeChantier.objects.create(
        projet=projet,
        nom="Ancienne Équipe Sans Membre Chef",
        nature="SOUS_TRAITANTE",
        corps_etat="Peinture",
        chef_nom="Ancien Chef Peintre",
    )
    assert equipe.membres.count() == 0

    migrer_chefs_et_nature(apps, None)

    equipe.refresh_from_db()
    assert equipe.nature == "SOUS_TRAITANT"
    chef_membre = equipe.membres.filter(fonction="CHEF_EQUIPE").first()
    assert chef_membre is not None
    assert chef_membre.nom == "Ancien Chef Peintre"


def test_ajouter_membre(contexte):
    client = contexte["client"]
    projet = contexte["projet"]
    user_ouvrier = contexte["user_ouvrier"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Maçonnerie"
    )

    url = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    corps = {
        "collaborateur_id": str(user_ouvrier.pk),
        "role": "OUVRIER_QUALIFIE",
    }
    response = client.post(url, corps, format="json")
    assert response.status_code == 201, response.data
    assert response.data["effectif"] == 1
    assert len(response.data["membres"]) == 1
    assert response.data["membres"][0]["collaborateur_id"] == str(user_ouvrier.pk)
    assert response.data["membres"][0]["role"] == "OUVRIER_QUALIFIE"


def test_membre_non_affecte_refuse(contexte):
    client = contexte["client"]
    projet = contexte["projet"]
    user_non_affecte = contexte["user_non_affecte"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Maçonnerie"
    )
    url = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    corps = {
        "collaborateur_id": str(user_non_affecte.pk),
        "role": "OUVRIER",
    }
    response = client.post(url, corps, format="json")
    assert response.status_code == 400
    assert "n'est pas affecté à ce projet" in response.json()["erreur"]["message"]


def test_doublon_refuse(contexte):
    client = contexte["client"]
    projet = contexte["projet"]
    user_ouvrier = contexte["user_ouvrier"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Maçonnerie"
    )
    url = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    corps = {
        "collaborateur_id": str(user_ouvrier.pk),
        "role": "OUVRIER",
    }
    resp1 = client.post(url, corps, format="json")
    assert resp1.status_code == 201

    resp2 = client.post(url, corps, format="json")
    assert resp2.status_code == 400
    assert "Une personne ne peut apparaître deux fois." in str(resp2.data)


def test_nommer_chef_retrograde_l_ancien(contexte):
    client = contexte["client"]
    projet = contexte["projet"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Maçonnerie"
    )
    url = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    resp_chef1 = client.post(url, {"nom": "Chef Ancien", "role": "CHEF_EQUIPE"}, format="json")
    assert resp_chef1.status_code == 201
    assert resp_chef1.data["chef"]["nom"] == "Chef Ancien"
    chef1_id = resp_chef1.data["chef"]["id"]

    resp_chef2 = client.post(url, {"nom": "Chef Nouveau", "role": "CHEF_EQUIPE"}, format="json")
    assert resp_chef2.status_code == 201
    assert resp_chef2.data["chef"]["nom"] == "Chef Nouveau"
    # L'ancien chef est maintenant dans membres comme OUVRIER_QUALIFIE
    ancien = next(m for m in resp_chef2.data["membres"] if m["id"] == chef1_id)
    assert ancien["role"] == "OUVRIER_QUALIFIE"
    # Exactement un seul chef
    assert (
        MembreEquipeChantier.objects.filter(
            equipe=equipe, fonction="CHEF_EQUIPE", supprime_le__isnull=True
        ).count()
        == 1
    )


def test_chef_qui_change_de_role_laisse_la_place(contexte):
    client = contexte["client"]
    projet = contexte["projet"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Maçonnerie"
    )
    url_base = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    resp = client.post(url_base, {"nom": "Chef Temporaire", "role": "CHEF_EQUIPE"}, format="json")
    membre_id = resp.data["chef"]["id"]

    # Modification de son rôle en OUVRIER
    patch_url = f"{url_base}{membre_id}/"
    patch_resp = client.patch(patch_url, {"role": "OUVRIER"}, format="json")
    assert patch_resp.status_code == 200
    assert patch_resp.data["chef"] is None
    assert patch_resp.data["chef_nom"] == ""
    assert patch_resp.data["effectif"] == 1


def test_retirer_membre(contexte):
    client = contexte["client"]
    projet = contexte["projet"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Maçonnerie"
    )
    url_base = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    resp = client.post(url_base, {"nom": "Ouvrier A Retirer", "role": "OUVRIER"}, format="json")
    membre_id = resp.data["membres"][0]["id"]
    assert resp.data["effectif"] == 1

    del_url = f"{url_base}{membre_id}/"
    del_resp = client.delete(del_url)
    assert del_resp.status_code == 204

    membre = MembreEquipeChantier.tous_objets.get(pk=membre_id)
    assert membre.supprime_le is not None

    get_resp = client.get(f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/")
    assert get_resp.data["effectif"] == 0
    assert len(get_resp.data["membres"]) == 0


def test_effectif_sans_chef(contexte):
    client = contexte["client"]
    projet = contexte["projet"]

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Sans Chef", nature="INTERNE", corps_etat="Maçonnerie"
    )
    url_base = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    for nom in ["Ouvrier 1", "Ouvrier 2", "Ouvrier 3"]:
        client.post(url_base, {"nom": nom, "role": "OUVRIER"}, format="json")

    get_resp = client.get(f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/")
    assert get_resp.data["effectif"] == 3
    assert get_resp.data["chef"] is None


def test_une_equipe_par_activite(contexte):
    client = contexte["client"]
    projet = contexte["projet"]
    activite = contexte["activite"]

    equipe_a = EquipeChantier.objects.create(
        projet=projet, nom="Équipe A", nature="INTERNE", corps_etat="Gros Œuvre"
    )
    equipe_b = EquipeChantier.objects.create(
        projet=projet, nom="Équipe B", nature="INTERNE", corps_etat="Gros Œuvre"
    )

    url_aff = f"/api/v1/projets/{projet.pk}/equipes/affectations/"
    # 1. Affecter Equipe A
    resp_a = client.post(
        url_aff,
        {"equipe_id": str(equipe_a.pk), "activite_id": str(activite.pk)},
        format="json",
    )
    assert resp_a.status_code == 201, resp_a.data

    # 2. Remplacer par Equipe B
    resp_b = client.post(
        url_aff,
        {"equipe_id": str(equipe_b.pk), "activite_id": str(activite.pk)},
        format="json",
    )
    assert resp_b.status_code == 201, resp_b.data
    assert resp_b.data["equipe_id"] == str(equipe_b.pk)

    # 3. Même équipe B -> 400
    resp_b_again = client.post(
        url_aff,
        {"equipe_id": str(equipe_b.pk), "activite_id": str(activite.pk)},
        format="json",
    )
    assert resp_b_again.status_code == 400
    assert "Équipe déjà affectée à cette activité." in str(resp_b_again.data)

    # 4. Vérifier equipe_chantier dans le serializer de l'activité
    url_act = f"/api/v1/activites/{activite.pk}/"
    resp_act = client.get(url_act)
    assert resp_act.status_code == 200
    assert resp_act.data["equipe_chantier"] is not None
    assert resp_act.data["equipe_chantier"]["id"] == str(equipe_b.pk)
    assert resp_act.data["equipe_chantier"]["nom"] == "Équipe B"


def test_membres_reserves_a_gerer_equipes(contexte):
    projet = contexte["projet"]
    user_visiteur = contexte["user_visiteur"]

    client_visiteur = APIClient(HTTP_HOST="demo.localhost")
    client_visiteur.force_authenticate(user_visiteur)

    equipe = EquipeChantier.objects.create(
        projet=projet, nom="Équipe Secrète", nature="INTERNE", corps_etat="Sécurité"
    )
    url_membres = f"/api/v1/projets/{projet.pk}/equipes/{equipe.pk}/membres/"
    resp = client_visiteur.post(url_membres, {"nom": "Intrus", "role": "OUVRIER"}, format="json")
    assert resp.status_code == 403
