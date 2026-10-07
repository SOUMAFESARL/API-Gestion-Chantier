"""Contrats de mutation, isolation projet et suppression logique."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Module, Role, RoleModulePermission, Utilisateur
from apps.core.enums import ModuleChoix, NiveauAcces, RoleGlobal, RoleProjet
from apps.projets.models import Activite, AffectationProjet, Lot, Projet

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexte(schema_demo):
    user = Utilisateur.objects.create_user(
        email="mutations.admin@demo.ci",
        password="Test12345!",
        nom="Admin",
        role_global=RoleGlobal.ADMIN,
    )
    projet = Projet.objects.create(reference="MUTATIONS", nom="Projet", ville="Man")
    lot = Lot.objects.create(
        projet=projet,
        code="L-01",
        libelle="Lot",
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
    )
    activite = Activite.objects.create(
        lot=lot,
        libelle="Activité",
        quantite_prevue=Decimal("10"),
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 10, 10),
    )
    activite.equipe.add(user)
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user)
    return client, projet, lot, activite, user


@pytest.mark.parametrize("ressource", ["lots", "activites"])
def test_patch_preserves_baseline_and_omitted_fields(contexte, ressource):
    client, _, lot, activite, _ = contexte
    objet = lot if ressource == "lots" else activite
    champ = "nom" if ressource == "lots" else "libelle"
    response = client.patch(f"/api/v1/{ressource}/{objet.pk}/", {champ: "Nouveau"}, format="json")
    assert response.status_code == 200, response.data
    objet.refresh_from_db()
    assert objet.libelle == "Nouveau"
    assert objet.date_debut_baseline == objet.date_debut_prevue
    assert objet.date_fin_baseline == objet.date_fin_prevue
    if ressource == "activites":
        assert objet.quantite_prevue == 10
        assert objet.equipe.count() == 1
    assert client.get(f"/api/v1/{ressource}/{objet.pk}/").status_code == 200


@pytest.mark.parametrize("ressource", ["lots", "activites"])
@pytest.mark.parametrize(
    "data",
    [
        {"date_fin_prevue": "2026-09-01"},
        {"budget_initial_montant": -1},
        {"est_actif": False},
        {"avancement": 50},
        {"projet_id": "inconnu"},
    ],
)
def test_invalid_patch_is_atomic(contexte, ressource, data):
    client, _, lot, activite, _ = contexte
    objet = lot if ressource == "lots" else activite
    response = client.patch(f"/api/v1/{ressource}/{objet.pk}/", data, format="json")
    assert response.status_code == 400, response.data
    objet.refresh_from_db()
    assert objet.est_actif
    assert objet.budget_initial_montant is None


def test_dates_consider_parent_children_and_existing_values(contexte):
    client, _, lot, activite, _ = contexte
    assert (
        client.patch(
            f"/api/v1/lots/{lot.pk}/", {"date_debut_prevue": "2026-10-06"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/v1/activites/{activite.pk}/", {"date_debut_prevue": "2026-09-30"}, format="json"
        ).status_code
        == 400
    )
    response = client.patch(
        f"/api/v1/activites/{activite.pk}/", {"date_fin_prevue": "2026-10-11"}, format="json"
    )
    assert response.status_code == 400, response.data
    assert "RG-11" in str(response.data)
    activite.refresh_from_db()
    assert activite.date_fin_baseline == date(2026, 10, 10)
    assert activite.date_fin_prevue == date(2026, 10, 10)


def test_initial_dates_can_be_filled_without_rewriting_baseline(contexte):
    client, _, lot, _, _ = contexte
    activite = Activite.objects.create(lot=lot, libelle="Sans dates", quantite_prevue=1)
    url = f"/api/v1/activites/{activite.pk}/"
    assert client.patch(url, {"date_fin_prevue": "2026-11-01"}, format="json").status_code == 400
    response = client.patch(
        url, {"date_debut_prevue": "2026-10-05", "date_fin_prevue": "2026-10-06"}, format="json"
    )
    assert response.status_code == 200, response.data
    activite.refresh_from_db()
    assert activite.date_debut_baseline == date(2026, 10, 5)


@pytest.mark.parametrize("ressource", ["lots", "activites"])
def test_activation_idempotent_and_strict(contexte, ressource):
    client, _, lot, activite, _ = contexte
    objet = lot if ressource == "lots" else activite
    url = f"/api/v1/{ressource}/{objet.pk}/activation/"
    for etat in (False, False, True):
        response = client.patch(url, {"est_actif": etat}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["est_actif"] is etat
        objet.refresh_from_db()
        assert objet.est_actif is etat
    for data in (
        {},
        {"est_actif": None},
        {"est_actif": "invalide"},
        {"est_actif": False, "libelle": "X"},
    ):
        assert client.patch(url, data, format="json").status_code == 400
    assert client.delete(url).status_code == 405


def test_inactive_lot_blocks_new_and_reactivated_activities(contexte):
    client, _, lot, activite, _ = contexte
    client.patch(f"/api/v1/lots/{lot.pk}/activation/", {"est_actif": False}, format="json")
    activite.refresh_from_db()
    assert activite.est_actif  # Pas de cascade implicite.
    assert (
        client.post(
            f"/api/v1/lots/{lot.pk}/activites/", {"libelle": "Nouvelle"}, format="json"
        ).status_code
        == 400
    )
    url = f"/api/v1/activites/{activite.pk}/activation/"
    assert client.patch(url, {"est_actif": False}, format="json").status_code == 200
    assert client.patch(url, {"est_actif": True}, format="json").status_code == 400


def test_soft_delete_and_lot_protection(contexte):
    client, _, lot, activite, user = contexte
    lot_url = f"/api/v1/lots/{lot.pk}/"
    activite_url = f"/api/v1/activites/{activite.pk}/"
    assert client.delete(lot_url).status_code == 400
    response = client.delete(activite_url)
    assert response.status_code == 204
    assert response.content == b""
    deleted = Activite.tous_objets.get(pk=activite.pk)
    assert deleted.supprime_le is not None
    assert deleted.supprime_par == user
    assert client.get(activite_url).status_code == 404
    assert (
        client.patch(activite_url + "activation/", {"est_actif": True}, format="json").status_code
        == 404
    )
    assert client.delete(lot_url).status_code == 204
    assert Lot.tous_objets.get(pk=lot.pk).supprime_par == user
    assert client.get(lot_url).status_code == 404


def test_dependence_cycles_successors_and_realized_quantity(contexte):
    client, _, lot, activite, _ = contexte
    suivant = Activite.objects.create(
        lot=lot,
        libelle="Suivant",
        quantite_prevue=1,
        dependance=activite,
        date_debut_prevue=date(2026, 10, 12),
    )
    url = f"/api/v1/activites/{activite.pk}/"
    assert client.patch(url, {"dependance": str(activite.pk)}, format="json").status_code == 400
    assert client.patch(url, {"dependance": str(suivant.pk)}, format="json").status_code == 400
    assert client.patch(url, {"date_fin_prevue": "2026-10-13"}, format="json").status_code == 400
    assert client.delete(url).status_code == 400
    activite.quantite_realisee = 5
    activite.save()
    assert client.patch(url, {"quantite_prevue": "4"}, format="json").status_code == 400
    assert client.patch(url, {"unite": "FORFAIT"}, format="json").status_code == 400
    assert (
        client.patch(
            f"/api/v1/activites/{suivant.pk}/", {"responsable_id": None}, format="json"
        ).status_code
        == 200
    )
    suivant.dependance = None
    suivant.save(update_fields=["dependance"])
    assert client.delete(url).status_code == 204


@pytest.mark.parametrize("ressource", ["lots", "activites"])
@pytest.mark.parametrize("action", ["patch", "delete", "activation"])
def test_anonymous_and_member_without_write_cannot_mutate(contexte, ressource, action):
    client, projet, lot, activite, _ = contexte
    objet = lot if ressource == "lots" else activite
    url = f"/api/v1/{ressource}/{objet.pk}/" + ("activation/" if action == "activation" else "")
    data = (
        {"est_actif": False}
        if action == "activation"
        else {"nom" if ressource == "lots" else "libelle": "Interdit"}
    )
    client.force_authenticate(None)
    response = client.delete(url) if action == "delete" else client.patch(url, data, format="json")
    assert response.status_code == 401
    visiteur = Utilisateur.objects.create_user(
        email="mutations.visiteur@demo.ci",
        password="Test12345!",
        nom="Visiteur",
        role_global=RoleGlobal.VISITEUR,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=visiteur, role_projet=RoleProjet.VISITEUR
    )
    client.force_authenticate(visiteur)
    response = client.delete(url) if action == "delete" else client.patch(url, data, format="json")
    assert response.status_code == 403
    objet.refresh_from_db()
    assert objet.est_actif
    assert objet.supprime_le is None


def test_deleted_parent_hides_activities(contexte):
    client, _, lot, activite, user = contexte
    lot.delete(utilisateur=user)
    assert client.get(f"/api/v1/activites/{activite.pk}/").status_code == 404
    assert (
        client.patch(
            f"/api/v1/activites/{activite.pk}/", {"libelle": "X"}, format="json"
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/lots/{lot.pk}/activites/").status_code == 404


@pytest.mark.parametrize("ressource", ["lots", "activites"])
def test_writer_needs_project_membership(contexte, ressource):
    client, projet, lot, activite, _ = contexte
    role = Role.objects.create(code="MUTATIONS_WRITER", libelle="Rédacteur")
    module, _ = Module.objects.get_or_create(
        code=ModuleChoix.PROJETS, defaults={"libelle": "Projets"}
    )
    RoleModulePermission.objects.create(role=role, module=module, niveau=NiveauAcces.ECRITURE)
    user = Utilisateur.objects.create_user(
        email="mutations.writer@demo.ci",
        password="Test12345!",
        nom="Rédacteur",
        role_global=RoleGlobal.VISITEUR,
        role_personnalise=role,
    )
    client.force_authenticate(user)
    objet = lot if ressource == "lots" else activite
    url = f"/api/v1/{ressource}/{objet.pk}/"
    data = {"nom" if ressource == "lots" else "libelle": "Autorisé"}
    assert client.patch(url, data, format="json").status_code == 403
    affectation = AffectationProjet.objects.create(
        projet=projet, utilisateur=user, role_projet=RoleProjet.VISITEUR
    )
    response = client.patch(url, data, format="json")
    assert response.status_code == 200, response.data
    affectation.est_actif = False
    affectation.save()
    assert client.patch(url + "activation/", {"est_actif": False}, format="json").status_code == 403


def test_patch_rejects_foreign_team_and_dependency(contexte):
    client, _, _, activite, _ = contexte
    autre = Projet.objects.create(reference="MUTATIONS-AUTRE", nom="Autre", ville="Man")
    autre_lot = Lot.objects.create(projet=autre, code="L-01", libelle="Autre")
    precedente = Activite.objects.create(lot=autre_lot, libelle="Précédente", quantite_prevue=1)
    user = Utilisateur.objects.create_user(
        email="mutations.horsprojet@demo.ci", password="Test12345!", nom="Autre"
    )
    url = f"/api/v1/activites/{activite.pk}/"
    assert client.patch(url, {"dependance": str(precedente.pk)}, format="json").status_code == 400
    assert client.patch(url, {"equipe_ids": [str(user.pk)]}, format="json").status_code == 400
    assert client.patch(url, {"equipe_ids": []}, format="json").status_code == 200
    assert not activite.equipe.exists()


@pytest.mark.parametrize("ressource", ["lots", "activites"])
def test_status_sent_on_creation_and_patch_persists(contexte, ressource):
    client, projet, lot, _, _ = contexte
    if ressource == "lots":
        url = f"/api/v1/projets/{projet.pk}/lots/"
        data = {"nom": "Lot manuel", "mode_execution": "REGIE", "type_bordereau": "FORFAIT"}
        model = Lot
    else:
        url = f"/api/v1/lots/{lot.pk}/activites/"
        data = {"libelle": "Activité manuelle"}
        model = Activite
    response = client.post(url, {**data, "statut": "EN_COURS"}, format="json")
    assert response.status_code == 201, response.data
    detail = f"/api/v1/{ressource}/{response.data['id']}/"
    assert response.data["statut"] == "EN_COURS"
    for statut in (
        "SUSPENDU",
        "CLOTURE",
        "Terminé",
        "en cours",
        "Statut personnalisé très long",
        "x" * 4096,
    ):
        response = client.patch(detail, {"statut": statut}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["statut"] == statut
        assert model.objects.get(pk=response.data["id"]).statut == statut
        assert client.get(detail).data["statut"] == statut
    response = client.patch(detail, {"statut": "INCONNU"}, format="json")
    assert response.status_code == 200
    assert response.data["statut"] == "INCONNU"


@pytest.mark.parametrize("ressource", ["lots", "activites"])
def test_motif_creation_patch_read_and_clear(contexte, ressource):
    client, projet, lot, activite, _ = contexte
    assert lot.motif == activite.motif == ""
    if ressource == "lots":
        url = f"/api/v1/projets/{projet.pk}/lots/"
        data = {"nom": "Lot", "mode_execution": "REGIE", "type_bordereau": "FORFAIT"}
        model = Lot
    else:
        url = f"/api/v1/lots/{lot.pk}/activites/"
        data = {"libelle": "Activité"}
        model = Activite
    motif = "  Suspendu pour intempéries  "
    response = client.post(url, {**data, "motif": motif}, format="json")
    assert response.status_code == 201, response.data
    assert response.data["motif"] == motif
    detail = f"/api/v1/{ressource}/{response.data['id']}/"
    assert client.get(detail).data["motif"] == motif
    assert model.objects.get(pk=response.data["id"]).motif == motif
    response = client.patch(detail, {"statut": "En attente"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["motif"] == motif
    response = client.patch(detail, {"motif": "Matériel livré"}, format="json")
    assert response.status_code == 200, response.data
    assert client.get(detail).data["motif"] == "Matériel livré"
    assert client.patch(detail, {"motif": None}, format="json").status_code == 400
    response = client.patch(detail, {"motif": ""}, format="json")
    assert response.status_code == 200, response.data
    assert client.get(detail).data["motif"] == ""
