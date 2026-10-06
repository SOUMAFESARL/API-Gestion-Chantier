"""Équipes de chantier, personnes et affectations indépendantes des accès RBAC."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet
from apps.projets.models import Activite, AffectationProjet, EquipeChantier, Lot, Projet

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexte(schema_demo):
    user = Utilisateur.objects.create_user(
        email="equipes.membre@demo.ci",
        password="Test12345!",
        nom="Membre",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
    )
    projet = Projet.objects.create(reference="PRJ-EQ", nom="Projet", ville="Man")
    AffectationProjet.objects.create(
        utilisateur=user,
        projet=projet,
        role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
    )
    lot = Lot.objects.create(projet=projet, code="L-01", libelle="Lot")
    a = Activite.objects.create(lot=lot, libelle="A", quantite_prevue=1)
    Activite.objects.create(lot=lot, libelle="B", quantite_prevue=1)
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    return client, projet, user, a


def payload(user):
    return {
        "nom": "Équipe Maçonnerie B",
        "nature": "INTERNE",
        "corps_etat": "Maçonnerie",
        "chef": {"nom": "Chef externe"},
        "membres": [{"utilisateur_id": str(user.pk)}, {"nom": "Ouvrier externe"}],
    }


def test_team_assignment_statistics_and_soft_delete(contexte):
    client, projet, user, activite = contexte
    base = f"/api/v1/projets/{projet.pk}/equipes/"
    stats = client.get(base + "statistiques/")
    assert stats.data == {
        "equipes_count": 0,
        "effectif_mobilise": 0,
        "activites_affectees": 0,
        "activites_a_affecter": 2,
    }
    created = client.post(base, payload(user), format="json")
    assert created.status_code == 201, created.data
    assert created.data["effectif"] == 3
    assert created.data["chef_nom"] == "Chef externe"
    assert len(created.data["membres"]) == 2
    assert len(client.get(base).data) == 1
    assignment = {"equipe_id": created.data["id"], "activite_id": str(activite.pk)}
    affectation = client.post(base + "affectations/", assignment, format="json")
    assert affectation.status_code == 201, affectation.data
    assert affectation.data["effectif"] == 3
    assert str(affectation.data["lot_id"]) == str(activite.lot_id)
    assert affectation.data["date_debut"] is None
    assert affectation.data["date_fin"] is None
    assert affectation.data["statut"] == activite.statut
    assert len(client.get(base + "affectations/", {"recherche": "Maçonnerie"}).data) == 1
    assert client.get(base + "affectations/", {"recherche": "Introuvable"}).data == []
    assert len(client.get(base + "affectations/", {"lot_id": str(activite.lot_id)}).data) == 1
    assert len(client.get(base + "affectations/", {"equipe_id": created.data["id"]}).data) == 1
    assert client.get(base + "affectations/", {"lot_id": "invalide"}).status_code == 400
    assert client.post(base + "affectations/", assignment, format="json").status_code == 400
    assert client.get(base + "statistiques/").data == {
        "equipes_count": 1,
        "effectif_mobilise": 3,
        "activites_affectees": 1,
        "activites_a_affecter": 1,
    }
    assert len(client.get(base + "affectations/").data) == 1
    assert client.delete(base + f"affectations/{affectation.data['id']}/").status_code == 204
    assert client.post(base + "affectations/", assignment, format="json").status_code == 201
    activite.statut = "CLOTURE"
    activite.save()
    assert client.get(base + "statistiques/").data["activites_a_affecter"] == 1
    assert client.get(base + "statistiques/").data["activites_affectees"] == 0
    assert client.post(base + "affectations/", assignment, format="json").status_code == 400
    assert client.delete(base + f"{created.data['id']}/").status_code == 204
    assert not EquipeChantier.objects.exists()
    assert EquipeChantier.tous_objets.count() == 1
    assert client.get(base + "statistiques/").data["effectif_mobilise"] == 0
    assert client.get(base + "affectations/").data == []


@pytest.mark.parametrize(
    "modification",
    [
        {"nom": ""},
        {"nature": "INVALIDE"},
        {"corps_etat": ""},
        {"chef": {}},
        {"chef": {"nom": "Chef externe", "utilisateur_id": "user"}},
        {"membres": [{"nom": "Chef externe"}]},
    ],
)
def test_invalid_team(contexte, modification):
    client, projet, user, _ = contexte
    if modification.get("chef", {}).get("utilisateur_id") == "user":
        modification = {"chef": {"nom": "Chef externe", "utilisateur_id": str(user.pk)}}
    result = client.post(
        f"/api/v1/projets/{projet.pk}/equipes/", {**payload(user), **modification}, format="json"
    )
    assert result.status_code == 400, result.data
    assert not EquipeChantier.objects.exists()


def test_cross_project_scope(contexte):
    client, projet, user, _ = contexte
    autre = Projet.objects.create(reference="PRJ-EQ-AUTRE", nom="Autre", ville="Man")
    base = f"/api/v1/projets/{projet.pk}/equipes/"
    foreign = f"/api/v1/projets/{autre.pk}/equipes/"
    assert client.post(foreign, payload(user), format="json").status_code == 403
    assert client.get(foreign + "statistiques/").status_code == 403
    outsider = Utilisateur.objects.create_user(
        email="equipes.externe@demo.ci",
        password="Test12345!",
        nom="Externe",
    )
    result = client.post(
        base, {**payload(user), "chef": {"utilisateur_id": str(outsider.pk)}}, format="json"
    )
    assert result.status_code == 400
    created = client.post(base, payload(user), format="json")
    foreign_lot = Lot.objects.create(projet=autre, code="L-01", libelle="Autre")
    foreign_activity = Activite.objects.create(lot=foreign_lot, libelle="Autre", quantite_prevue=1)
    assert (
        client.post(
            base + "affectations/",
            {
                "equipe_id": created.data["id"],
                "activite_id": str(foreign_activity.pk),
            },
            format="json",
        ).status_code
        == 404
    )
    client.force_authenticate(None)
    assert client.get(base).status_code in (401, 403)


def test_multiple_teams_do_not_double_count_activity(contexte):
    client, projet, user, activite = contexte
    base = f"/api/v1/projets/{projet.pk}/equipes/"
    for numero in (1, 2):
        team = client.post(base, {**payload(user), "nom": f"Équipe {numero}"}, format="json")
        assert team.status_code == 201
        assert (
            client.post(
                base + "affectations/",
                {
                    "equipe_id": team.data["id"],
                    "activite_id": str(activite.pk),
                },
                format="json",
            ).status_code
            == 201
        )
    stats = client.get(base + "statistiques/").data
    assert stats["equipes_count"] == 2
    assert stats["effectif_mobilise"] == 5
    assert stats["activites_affectees"] == 1
