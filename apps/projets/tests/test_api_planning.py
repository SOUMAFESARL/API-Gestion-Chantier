"""Tests de `GET /api/v1/projets/{id}/planning/` (SFD F3 §5.2, §5.3, §13)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import RoleGlobal, RoleProjet, StatutActivite
from apps.projets.models import Activite, AffectationProjet, Lot, Projet

HOTE = "demo.localhost"

CLES_RACINE = {"aujourdhui", "lots"}
CLES_LOT = {
    "id",
    "code",
    "libelle",
    "debut",
    "fin",
    "avancement",
    "avancement_temporel",
    "delta_retard",
    "activites",
}
CLES_ACTIVITE = {"id", "libelle", "debut", "fin", "avancement", "statut"}


@pytest.fixture
def acteurs(schema_demo):
    initialiser_roles_par_defaut()
    dg = Utilisateur.objects.create_user(
        email="dg_planning@demo.ci",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        nom="DG",
        prenom="Planning",
    )
    cp_affecte = Utilisateur.objects.create_user(
        email="cp_planning@demo.ci",
        role_global=RoleGlobal.CHEF_PROJET,
        nom="CP",
        prenom="Affecte",
    )
    cp_externe = Utilisateur.objects.create_user(
        email="cp_externe_planning@demo.ci",
        role_global=RoleGlobal.CHEF_PROJET,
        nom="CP",
        prenom="Externe",
    )
    return {"dg": dg, "cp_affecte": cp_affecte, "cp_externe": cp_externe}


@pytest.fixture
def projet(acteurs):
    projet = Projet.objects.create(
        reference="PRJ-PLANNING-001",
        nom="Chantier planning",
        chef_projet=acteurs["cp_affecte"],
        date_debut_prevue=date(2020, 1, 1),
        date_fin_prevue=date(2020, 12, 31),
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=acteurs["cp_affecte"],
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
    )
    return projet


def _client(utilisateur) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=utilisateur)
    return client


def _lire(utilisateur, projet):
    return _client(utilisateur).get(f"/api/v1/projets/{projet.id}/planning/", HTTP_HOST=HOTE)


def _creer_lot(projet, ordre, *, code=None, **extra) -> Lot:
    lot = Lot.objects.create(
        projet=projet,
        code=code or f"LOT-{ordre:02d}",
        libelle=f"Lot {ordre}",
        ordre=ordre,
        date_debut_prevue=date(2020, 1, 6),
        date_fin_prevue=date(2020, 1, 10),
        **extra,
    )
    for rang in (1, 2, 3):
        Activite.objects.create(
            lot=lot,
            libelle=f"Activité {ordre}.{rang}",
            ordre=rang,
            quantite_prevue=Decimal("10"),
            quantite_realisee=Decimal("2.5"),
            unite="M3",
        )
    return lot


@pytest.mark.django_db
def test_forme_exacte_du_payload(acteurs, projet):
    _creer_lot(projet, 1)

    rep = _lire(acteurs["dg"], projet)

    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert set(data) == CLES_RACINE
    assert data["aujourdhui"] == timezone.localdate().isoformat()
    assert len(data["lots"]) == 1
    lot = data["lots"][0]
    assert set(lot) == CLES_LOT
    assert len(lot["activites"]) == 3
    for activite in lot["activites"]:
        assert set(activite) == CLES_ACTIVITE


@pytest.mark.django_db
def test_valeurs_d_un_lot_connu(acteurs, projet):
    lot = _creer_lot(projet, 1)
    activite_cloturee = lot.activites.get(ordre=1)
    activite_cloturee.statut = StatutActivite.CLOTURE
    activite_cloturee.save(update_fields=["statut"])
    # 1 activité clôturée (100 %) et 2 à 25 % : (100 + 25 + 25) / 3 = 50,0
    # Le lot est entièrement dans le passé : avancement temporel 100 %, retard 50 points.

    data = _lire(acteurs["dg"], projet).json()

    lot_rendu = data["lots"][0]
    assert lot_rendu["id"] == str(lot.id)
    assert lot_rendu["code"] == "LOT-01"
    assert lot_rendu["libelle"] == "Lot 1"
    assert lot_rendu["debut"] == "2020-01-06"
    assert lot_rendu["fin"] == "2020-01-10"
    assert lot_rendu["avancement"] == 50.0
    assert lot_rendu["avancement_temporel"] == 100.0
    assert lot_rendu["delta_retard"] == 50.0
    premiere, deuxieme, troisieme = lot_rendu["activites"]
    assert premiere["libelle"] == "Activité 1.1"
    assert premiere["avancement"] == 100.0
    assert premiere["statut"] == StatutActivite.CLOTURE
    assert deuxieme["avancement"] == 25.0
    assert deuxieme["statut"] == StatutActivite.PLANIFIE
    assert troisieme["avancement"] == 25.0
    assert deuxieme["debut"] is None
    assert deuxieme["fin"] is None


@pytest.mark.django_db
def test_dates_baseline_prioritaires_sur_prevues(acteurs, projet):
    lot = _creer_lot(projet, 1)
    Lot.objects.filter(pk=lot.pk).update(
        date_debut_baseline=date(2020, 1, 1), date_fin_baseline=date(2020, 1, 31)
    )

    lot_rendu = _lire(acteurs["dg"], projet).json()["lots"][0]

    assert lot_rendu["debut"] == "2020-01-01"
    assert lot_rendu["fin"] == "2020-01-31"


@pytest.mark.django_db
def test_lot_sans_dates_rend_des_valeurs_nulles(acteurs, projet):
    Lot.objects.create(projet=projet, code="LOT-ND", libelle="Sans dates", ordre=1)

    lot_rendu = _lire(acteurs["dg"], projet).json()["lots"][0]

    assert lot_rendu["debut"] is None
    assert lot_rendu["fin"] is None
    assert lot_rendu["avancement_temporel"] is None
    assert lot_rendu["delta_retard"] is None
    assert lot_rendu["activites"] == []


@pytest.mark.django_db
def test_pourcentages_a_une_decimale(acteurs, projet):
    lot = _creer_lot(projet, 1)
    Activite.objects.filter(lot=lot).update(
        quantite_prevue=Decimal("3"), quantite_realisee=Decimal("1")
    )

    lot_rendu = _lire(acteurs["dg"], projet).json()["lots"][0]

    assert lot_rendu["avancement"] == 33.3
    for activite in lot_rendu["activites"]:
        assert activite["avancement"] == 33.3
    assert lot_rendu["delta_retard"] == 66.7


@pytest.mark.django_db
def test_tri_par_ordre_et_exclusion_des_inactifs_et_supprimes(acteurs, projet):
    lot_trois = _creer_lot(projet, 3)
    _creer_lot(projet, 1)
    _creer_lot(projet, 2)
    inactif = _creer_lot(projet, 4)
    Lot.objects.filter(pk=inactif.pk).update(est_actif=False)
    supprime = _creer_lot(projet, 5)
    Lot.objects.filter(pk=supprime.pk).update(supprime_le=timezone.now())
    Activite.objects.filter(lot=lot_trois, ordre=1).update(ordre=9)
    Activite.objects.filter(lot=lot_trois, ordre=2).update(est_actif=False)
    Activite.objects.filter(lot=lot_trois, ordre=3).update(supprime_le=timezone.now())

    lots = _lire(acteurs["dg"], projet).json()["lots"]

    assert [lot["code"] for lot in lots] == ["LOT-01", "LOT-02", "LOT-03"]
    assert [a["libelle"] for a in lots[2]["activites"]] == ["Activité 3.1"]


@pytest.mark.django_db
def test_nombre_de_requetes_constant(acteurs, projet, django_assert_max_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _creer_lot(projet, 1)
    _lire(acteurs["dg"], projet)  # amorce les caches éventuels

    with CaptureQueriesContext(connection) as capture:
        rep = _lire(acteurs["dg"], projet)
    assert rep.status_code == status.HTTP_200_OK
    assert len(rep.json()["lots"]) == 1
    requetes_pour_un_lot = len(capture)

    for ordre in range(2, 6):
        _creer_lot(projet, ordre)

    with django_assert_max_num_queries(requetes_pour_un_lot):
        rep = _lire(acteurs["dg"], projet)
    assert rep.status_code == status.HTTP_200_OK
    assert len(rep.json()["lots"]) == 5


@pytest.mark.django_db
def test_chef_de_projet_affecte_peut_lire(acteurs, projet):
    _creer_lot(projet, 1)

    rep = _lire(acteurs["cp_affecte"], projet)

    assert rep.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_refus_sans_acces_au_projet(acteurs, projet):
    _creer_lot(projet, 1)

    rep = _lire(acteurs["cp_externe"], projet)

    assert rep.status_code == status.HTTP_403_FORBIDDEN
    assert "erreur" in rep.json()


@pytest.mark.django_db
def test_refus_sans_authentification(projet):
    rep = APIClient().get(f"/api/v1/projets/{projet.id}/planning/", HTTP_HOST=HOTE)

    assert rep.status_code == status.HTTP_401_UNAUTHORIZED
