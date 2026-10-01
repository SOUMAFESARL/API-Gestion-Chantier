"""Régressions du cycle de vie projet dans un schéma tenant réel."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db


def test_creation_maitre_ouvrage_texte_et_modification(scenario):
    client, projet, _, cp, *_ = scenario
    nombre_tiers = Tiers.objects.count()
    data = {
        "nom": "Saisie libre",
        "maitre_ouvrage": "Mon maître d'ouvrage",
        "maitre_oeuvre": "Cabinet",
        "ville": "Adjamé",
        "date_debut_prevue": "2026-10-01",
        "date_fin_prevue": "2026-12-31",
        "chef_projet_id": str(cp.pk),
        "lots": [{"libelle": "Lot 1"}, {"libelle": "Lot 2"}],
    }
    response = client.post("/api/v1/projets/", data, format="json")
    assert response.status_code == 201, response.data
    assert response.data["maitre_ouvrage"] == data["maitre_ouvrage"]
    assert response.data["client"] is None
    assert len(response.data["lots"]) == 2
    assert Tiers.objects.count() == nombre_tiers
    url = f"/api/v1/projets/{response.data['id']}/"
    response = client.patch(url, {"maitre_ouvrage": "Autre nom"}, format="json")
    assert response.status_code == 200
    assert client.get(url).data["maitre_ouvrage"] == "Autre nom"
    ancien = client.get(f"/api/v1/projets/{projet.pk}/")
    assert ancien.data["maitre_ouvrage"] == projet.client.raison_sociale


@pytest.mark.parametrize("valeur", ["", "   ", None])
def test_maitre_ouvrage_vide_refuse(scenario, valeur):
    client, projet, *_ = scenario
    response = client.patch(
        f"/api/v1/projets/{projet.pk}/",
        {"maitre_ouvrage": valeur},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "lots",
    [
        [{"libelle": "Automatique"}, {"libelle": "Explicite", "code": "L-01"}],
        [{"libelle": "Explicite", "code": "L-02"}, {"libelle": "Automatique"}],
    ],
)
def test_creation_codes_mixtes_sans_collision(scenario, lots):
    client, projet, admin, cp, *_ = scenario
    client.force_authenticate(None)
    connexion = client.post(
        "/api/v1/auth/token/",
        {
            "email": admin.email,
            "mot_de_passe": "Test12345!",
            "origine": "WEB",
        },
        format="json",
    )
    assert connexion.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {connexion.data['access']}")
    response = client.post(
        "/api/v1/projets/",
        {
            "nom": "Formulaire plusieurs lots",
            "client": str(projet.client_id),
            "ville": "Adjamé",
            "date_debut_prevue": "2026-10-01",
            "date_fin_prevue": "2026-12-31",
            "chef_projet_id": str(cp.pk),
            "lots": lots,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    codes = [lot["code"] for lot in response.data["lots"]]
    assert len(codes) == len(set(codes)) == 2
    assert Lot.objects.filter(projet_id=response.data["id"]).count() == 2


@pytest.fixture
def scenario(schema_demo):
    def user(nom, role):
        return Utilisateur.objects.create_user(
            email=f"{nom}.crud@demo.ci",
            password="Test12345!",
            nom=nom,
            role_global=role,
            statut=StatutUtilisateur.ACTIF,
        )

    admin = user("admin", RoleGlobal.ADMIN)
    cp = user("cp", RoleGlobal.CHEF_PROJET)
    ct = user("ct", RoleGlobal.CONDUCTEUR_TRAVAUX)
    autre = user("autre", RoleGlobal.CHEF_PROJET)
    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(admin)
    tiers = Tiers.objects.create(raison_sociale="Client CRUD", type_tiers="ENTREPRISE")
    projet = Projet.objects.create(
        reference="CRUD-001",
        nom="ZRAN",
        client=tiers,
        ville="Adjamé",
        chef_projet=cp,
        conducteur_travaux=ct,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    for membre, role in [(cp, RoleProjet.CHEF_PROJET), (ct, RoleProjet.CONDUCTEUR_TRAVAUX)]:
        AffectationProjet.objects.create(projet=projet, utilisateur=membre, role_projet=role)
    return client, projet, admin, cp, ct, autre


def test_suppression_logique_et_routes_inaccessibles(scenario):
    client, projet, admin, *_ = scenario
    lot = Lot.objects.create(projet=projet, code="L-01", libelle="Fondations")
    url = f"/api/v1/projets/{projet.pk}/"
    assert client.get(url).status_code == 200
    assert client.delete(url).status_code == 204
    projet.refresh_from_db()
    assert projet.supprime_le is not None
    assert projet.supprime_par_id == admin.pk
    assert Lot.objects.filter(pk=lot.pk).exists()
    assert not Projet.objects.filter(pk=projet.pk).exists()
    assert str(projet.pk) not in [p["id"] for p in client.get("/api/v1/projets/").data]
    assert client.get(url).status_code == 404
    assert client.patch(url, {"nom": "Non"}, format="json").status_code == 404
    assert client.delete(url).status_code == 404


def test_remplacement_cp_et_retrait_ct(scenario):
    client, projet, _, cp, ct, autre = scenario
    url = f"/api/v1/projets/{projet.pk}/"
    response = client.patch(
        url,
        {
            "chef_projet_id": str(autre.pk),
            "conducteur_travaux_id": None,
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    projet.refresh_from_db()
    assert projet.chef_projet_id == autre.pk
    assert projet.conducteur_travaux_id is None
    assert not AffectationProjet.objects.filter(
        projet=projet,
        utilisateur__in=[cp, ct],
        est_actif=True,
    ).exists()
    assert AffectationProjet.objects.get(projet=projet, utilisateur=autre).est_actif
    # Réactiver l'affectation historique respecte sa contrainte d'unicité.
    assert client.patch(url, {"chef_projet_id": str(cp.pk)}, format="json").status_code == 200
    assert AffectationProjet.objects.get(projet=projet, utilisateur=cp).est_actif


@pytest.mark.parametrize(
    "data",
    [
        {"equipe": {}},
        {"visiteurs_ids": []},
        {"reference": ""},
        {"date_fin_prevue": "2026-09-01"},
    ],
)
def test_patch_invalide_ne_modifie_pas(scenario, data):
    client, projet, *_ = scenario
    response = client.patch(f"/api/v1/projets/{projet.pk}/", data, format="json")
    assert response.status_code == 400
    projet.refresh_from_db()
    assert projet.reference == "CRUD-001"


def test_responsable_inactif_ou_deja_affecte_refuse(scenario):
    client, projet, _, cp, ct, autre = scenario
    url = f"/api/v1/projets/{projet.pk}/"
    assert client.patch(url, {"chef_projet_id": str(ct.pk)}, format="json").status_code == 400
    autre.is_active = False
    autre.save()
    assert client.patch(url, {"chef_projet_id": str(autre.pk)}, format="json").status_code == 400
    projet.refresh_from_db()
    assert projet.chef_projet_id == cp.pk


def test_suppression_interdite_sans_acces(scenario):
    client, projet, _, _, _, autre = scenario
    client.force_authenticate(autre)
    assert client.delete(f"/api/v1/projets/{projet.pk}/").status_code == 403
    client.force_authenticate(None)
    assert client.delete(f"/api/v1/projets/{projet.pk}/").status_code == 401
    projet.refresh_from_db()
    assert projet.supprime_le is None


def test_ajouter_et_supprimer_plusieurs_lots(scenario):
    client, projet, admin, *_ = scenario
    lots = [
        Lot.objects.create(projet=projet, code=f"L-{i:02d}", libelle="Lot") for i in range(1, 4)
    ]
    response = client.patch(
        f"/api/v1/projets/{projet.pk}/",
        {
            "lots": [{"libelle": "Electricité"}, {"libelle": "Plomberie", "code": "L-04"}],
            "lots_supprimer_ids": [str(lot.pk) for lot in lots[:2]],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert len(response.data["lots"]) == 3
    assert Lot.objects.filter(pk=lots[2].pk).exists()
    for lot in lots[:2]:
        lot.refresh_from_db()
        assert lot.supprime_le and lot.supprime_par_id == admin.pk
        assert not lot.est_actif
    assert Lot.objects.filter(projet=projet, cree_par=admin).count() == 2


@pytest.mark.parametrize("nouveaux", [[{}], [{"libelle": "Doublon", "code": "L-02"}]])
def test_lot_invalide_annule_toute_modification(scenario, nouveaux):
    client, projet, *_ = scenario
    premier = Lot.objects.create(projet=projet, code="L-01", libelle="Premier")
    Lot.objects.create(projet=projet, code="L-02", libelle="Second")
    response = client.patch(
        f"/api/v1/projets/{projet.pk}/",
        {
            "nom": "Ne pas enregistrer",
            "lots": nouveaux,
            "lots_supprimer_ids": [str(premier.pk)],
        },
        format="json",
    )
    assert response.status_code == 400
    projet.refresh_from_db()
    assert projet.nom == "ZRAN"
    assert Lot.objects.filter(projet=projet).count() == 2


def test_lot_exterieur_refuse_et_liste_vide_sans_effet(scenario):
    from uuid import uuid4

    client, projet, *_ = scenario
    Lot.objects.create(projet=projet, code="L-01", libelle="Conservé")
    url = f"/api/v1/projets/{projet.pk}/"
    response = client.patch(
        url,
        {
            "lots": [{"libelle": "Ajout"}],
            "lots_supprimer_ids": [str(uuid4())],
        },
        format="json",
    )
    assert response.status_code == 400
    assert (
        client.patch(url, {"lots": [], "lots_supprimer_ids": []}, format="json").status_code == 200
    )
    assert Lot.objects.filter(projet=projet).count() == 1


def test_suppression_lot_conserve_son_rapport(scenario):
    from apps.chantier.models import RapportJournalier

    client, projet, admin, *_ = scenario
    lot = Lot.objects.create(projet=projet, code="L-01", libelle="Fondations")
    rapport = RapportJournalier.objects.create(projet=projet, lot=lot, auteur=admin)
    response = client.patch(
        f"/api/v1/projets/{projet.pk}/",
        {"lots_supprimer_ids": [str(lot.pk)]},
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["lots"] == []
    rapport.refresh_from_db()
    assert rapport.lot_id == lot.pk
    assert rapport.supprime_le is None
    assert Lot.tous_objets.get(pk=lot.pk).supprime_le is not None


def test_lot_autre_projet_refuse(scenario):
    client, projet, *_ = scenario
    autre_projet = Projet.objects.create(
        reference="AUTRE",
        nom="Autre",
        client=projet.client,
        ville=projet.ville,
        chef_projet=projet.chef_projet,
        date_debut_prevue=projet.date_debut_prevue,
        date_fin_prevue=projet.date_fin_prevue,
    )
    lot = Lot.objects.create(projet=autre_projet, code="L-01", libelle="Autre")
    response = client.patch(
        f"/api/v1/projets/{projet.pk}/",
        {"lots_supprimer_ids": [str(lot.pk)], "lots": [{"libelle": "Ajout"}]},
        format="json",
    )
    assert response.status_code == 400
    assert Lot.objects.filter(pk=lot.pk).exists()
    assert not Lot.objects.filter(projet=projet).exists()


def test_modification_lots_interdite_sans_affectation(scenario):
    client, projet, _, _, _, autre = scenario
    lot = Lot.objects.create(projet=projet, code="L-01", libelle="Conservé")
    client.force_authenticate(autre)
    response = client.patch(
        f"/api/v1/projets/{projet.pk}/",
        {"lots_supprimer_ids": [str(lot.pk)], "lots": [{"libelle": "Ajout"}]},
        format="json",
    )
    assert response.status_code == 403
    assert list(Lot.objects.filter(projet=projet).values_list("pk", flat=True)) == [lot.pk]
