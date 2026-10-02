"""Parcours lots -> activités et statistiques calculées automatiquement."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet
from apps.projets.models import Activite, AffectationProjet, Lot, Projet

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexte(schema_demo):
    user = Utilisateur.objects.create_user(
        email="activites.membre@demo.ci",
        password="Test12345!",
        nom="Membre",
        role_global=RoleGlobal.VISITEUR,
    )
    projet = Projet.objects.create(reference="PRJ-ACT", nom="Projet", ville="Man")
    AffectationProjet.objects.create(
        utilisateur=user,
        projet=projet,
        role_projet=RoleProjet.VISITEUR,
    )
    lot = Lot.objects.create(projet=projet, code="L-01", libelle="Fondations")
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    return client, projet, lot, user


def test_creation_and_statistics(contexte):
    client, projet, lot, user = contexte
    url = f"/api/v1/lots/{lot.pk}/activites/"
    stats = f"/api/v1/projets/{projet.pk}/statistiques/"
    assert client.get(stats).data["activites_count"] == 0
    created = client.post(
        url, {"libelle": "Terrassement", "equipe_ids": [str(user.pk)]}, format="json"
    )
    assert created.status_code == 201, created.data
    assert str(created.data["lot_id"]) == str(lot.pk)
    assert created.data["date_debut_prevue"] is None
    assert created.data["date_fin_prevue"] is None
    assert Decimal(created.data["quantite_prevue"]) == 1
    assert str(created.data["equipe_ids"][0]) == str(user.pk)
    assert len(client.get(url).data) == 1
    autre_lot = Lot.objects.create(projet=projet, code="L-02", libelle="Structure")
    second = client.post(
        f"/api/v1/lots/{autre_lot.pk}/activites/",
        {
            "libelle": "Coffrage",
            "quantite_prevue": "100",
            "unite": "M2",
            "dependance": created.data["id"],
        },
        format="json",
    )
    assert second.status_code == 201, second.data
    a = Activite.objects.get(pk=created.data["id"])
    a.quantite_realisee = Decimal("0.5")
    a.budget_initial_montant = 10000
    a.save()
    b = Activite.objects.get(pk=second.data["id"])
    b.budget_initial_montant = 30000
    b.date_fin_prevue = timezone.localdate() - timedelta(days=1)
    b.save()
    result = client.get(stats)
    assert result.status_code == 200
    assert result.data == {
        "lots_count": 2,
        "activites_count": 2,
        "avancement_pondere": 12.5,
        "ponderation": "BUDGET",
        "activites_en_retard": 1,
        "budget_activites_montant": 40000,
    }
    direction = Utilisateur.objects.create_user(
        email="statistiques.direction@demo.ci", password="Test12345!",
        nom="Direction", role_global=RoleGlobal.ADMIN,
    )
    lecteur = APIClient(HTTP_HOST="demo.localhost")
    lecteur.force_authenticate(direction)
    for response in (
        lecteur.get(f"/api/v1/projets/{projet.pk}/"),
        lecteur.get("/api/v1/projets/"),
    ):
        assert response.status_code == 200, response.data
        data = response.data[0] if isinstance(response.data, list) else response.data
        assert data["statistiques"] == result.data
    b.est_actif = False
    b.save()
    assert client.get(stats).data["activites_count"] == 1
    assert client.get(stats).data["avancement_pondere"] == 50


@pytest.mark.parametrize(
    "extra",
    [
        {"quantite_prevue": 0},
        {"unite": "FAUX"},
        {"budget_initial_montant": -1},
        {"date_debut_prevue": "2026-10-11", "date_fin_prevue": "2026-10-04"},
        {"quantite_realisee": 2},
        {"lot_id": "FAUX"},
    ],
)
def test_validation(contexte, extra):
    client, _, lot, _ = contexte
    result = client.post(
        f"/api/v1/lots/{lot.pk}/activites/",
        {
            "libelle": "Activité",
            **extra,
        },
        format="json",
    )
    assert result.status_code == 400, result.data
    assert not lot.activites.exists()


def test_dependency_team_scope_and_permissions(contexte):
    client, projet, lot, _ = contexte
    other = Projet.objects.create(reference="PRJ-OTHER-ACT", nom="Autre", ville="Man")
    other_lot = Lot.objects.create(projet=other, code="L-01", libelle="Autre")
    previous = Activite.objects.create(
        lot=other_lot,
        libelle="Précédente",
        quantite_prevue=1,
    )
    url = f"/api/v1/lots/{lot.pk}/activites/"
    assert (
        client.post(
            url, {"libelle": "Activité", "dependance": str(previous.pk)}, format="json"
        ).status_code
        == 400
    )
    outsider = Utilisateur.objects.create_user(
        email="activites.externe@demo.ci",
        password="Test12345!",
        nom="Externe",
    )
    assert (
        client.post(
            url, {"libelle": "Activité", "equipe_ids": [str(outsider.pk)]}, format="json"
        ).status_code
        == 400
    )
    assert client.get(f"/api/v1/projets/{other.pk}/statistiques/").status_code == 403
    assert (
        client.post(
            f"/api/v1/lots/{other_lot.pk}/activites/", {"libelle": "Interdit"}, format="json"
        ).status_code
        == 403
    )
    lot.est_actif = False
    lot.save()
    assert client.post(url, {"libelle": "Interdit"}, format="json").status_code == 400
    client.force_authenticate(None)
    assert client.get(f"/api/v1/projets/{projet.pk}/statistiques/").status_code in (401, 403)
