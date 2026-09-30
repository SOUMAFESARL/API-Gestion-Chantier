"""Tests complets pour la reprogrammation de dates, la Baseline v0 et l'alerte Celery (US-033, RG-11)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, StatutUtilisateur, UniteMesure
from apps.projets.models import (
    Activite,
    AffectationProjet,
    HistoriqueDate,
    Lot,
    MotifReport,
    Projet,
    TypeObjetHistorique,
)
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db


@pytest.fixture
def environnement_chantier(schema_demo):
    """Prépare un environnement complet avec DG, CP, projet, lot, activité et motifs."""
    from apps.accounts.services.roles import initialiser_roles_par_defaut
    initialiser_roles_par_defaut()

    def user(nom, role):
        return Utilisateur.objects.create_user(
            email=f"{nom}.reprog@demo.ci",
            password="Test12345!",
            nom=nom,
            role_global=role,
            statut=StatutUtilisateur.ACTIF,
        )

    dg = user("dg", RoleGlobal.DIRECTEUR_GENERAL)
    admin = user("admin", RoleGlobal.ADMIN)
    cp = user("cp", RoleGlobal.CHEF_PROJET)
    tiers = Tiers.objects.create(raison_sociale="Client BTP Test", type_tiers="ENTREPRISE")

    projet = Projet.objects.create(
        reference="PRJ-REPROG-01",
        nom="Chantier Résidence Ivoire",
        client=tiers,
        ville="Abidjan",
        chef_projet=cp,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=cp,
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
    )

    lot = Lot.objects.create(
        projet=projet,
        code="LOT-GROS-OEUVRE",
        libelle="Gros Œuvre",
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 12, 15),
    )

    activite = Activite.objects.create(
        lot=lot,
        libelle="Coulage dalle RDC",
        unite=UniteMesure.METRE_CUBE,
        quantite_prevue=Decimal("50.000"),
        date_debut_prevue=date(2026, 10, 10),
        date_fin_prevue=date(2026, 10, 25),
    )

    # Motifs par défaut
    motif_intemperies = MotifReport.objects.filter(code="INTEMPERIES").first()
    if not motif_intemperies:
        motif_intemperies = MotifReport.objects.create(
            code="INTEMPERIES",
            libelle="Intempéries",
            ordre=1,
            est_actif=True,
        )

    motif_inactif = MotifReport.objects.create(
        code="ANCIEN_MOTIF",
        libelle="Motif Désactivé",
        ordre=99,
        est_actif=False,
    )

    client_cp = APIClient(headers={"host": "demo.localhost"})
    client_cp.force_authenticate(cp)

    client_admin = APIClient(headers={"host": "demo.localhost"})
    client_admin.force_authenticate(admin)

    return {
        "dg": dg,
        "admin": admin,
        "cp": cp,
        "projet": projet,
        "lot": lot,
        "activite": activite,
        "motif_intemperies": motif_intemperies,
        "motif_inactif": motif_inactif,
        "client_cp": client_cp,
        "client_admin": client_admin,
    }


def test_baseline_v0_initialisee_automatiquement_et_immuable(environnement_chantier):
    """Vérifie que la Baseline v0 est figée à la création et protégée contre toute modification."""
    env = environnement_chantier
    p = env["projet"]
    l = env["lot"]
    a = env["activite"]

    # 1. Vérification de l'initialisation automatique
    assert p.date_debut_baseline == date(2026, 10, 1)
    assert p.date_fin_baseline == date(2026, 12, 31)

    assert l.date_debut_baseline == date(2026, 10, 5)
    assert l.date_fin_baseline == date(2026, 12, 15)

    assert a.date_debut_baseline == date(2026, 10, 10)
    assert a.date_fin_baseline == date(2026, 10, 25)

    # 2. Tentative de modifier la baseline via PATCH sur Projet -> Refusé
    client = env["client_cp"]
    res = client.patch(
        f"/api/v1/projets/{p.pk}/",
        {"date_fin_baseline": "2027-05-01"},
        format="json",
    )
    assert res.status_code == 400
    assert "Baseline v0" in str(res.data)


def _details(res):
    return res.data.get("erreur", {}).get("details", res.data)


def test_rejet_justification_inferieure_a_30_caracteres(environnement_chantier):
    """RG-11 : Toute modification de date prévisionnelle exige au moins 30 caractères."""
    env = environnement_chantier
    client = env["client_cp"]
    p = env["projet"]
    motif = env["motif_intemperies"]

    res = client.post(
        f"/api/v1/projets/{p.pk}/reprogrammer/",
        {
            "date_fin_prevue": "2027-01-15",
            "motif_id": str(motif.id),
            "justification": "Trop court !",  # < 30 caractères
        },
        format="json",
    )
    assert res.status_code == 400
    details = _details(res)
    assert "justification" in details
    assert "30" in str(details["justification"]) and "caract" in str(details["justification"])


def test_rejet_motif_inactif_ou_inconnu(environnement_chantier):
    """Vérifie le rejet d'un motif désactivé ou inexistant."""
    env = environnement_chantier
    client = env["client_cp"]
    p = env["projet"]
    motif_inactif = env["motif_inactif"]

    res = client.post(
        f"/api/v1/projets/{p.pk}/reprogrammer/",
        {
            "date_fin_prevue": "2027-01-15",
            "motif_id": str(motif_inactif.id),
            "justification": "Justification de plus de 30 caractères pour test d'inactivité.",
        },
        format="json",
    )
    assert res.status_code == 400
    details = _details(res)
    assert "motif_id" in details
    assert "inactif" in str(details["motif_id"])


def test_coherence_hierarchique_activite_lot(environnement_chantier):
    """Une activité ne peut jamais dépasser les dates de son lot parent."""
    env = environnement_chantier
    client = env["client_cp"]
    activite = env["activite"]
    motif = env["motif_intemperies"]

    # Le lot finit le 15/12/2026. Tenter de finir l'activité le 20/12/2026 doit échouer.
    res = client.post(
        f"/api/v1/activites/{activite.pk}/reprogrammer/",
        {
            "date_fin_prevue": "2026-12-20",
            "motif_id": str(motif.id),
            "justification": "Retard approvisionnement sable de lagune conforme aux exigences.",
        },
        format="json",
    )
    assert res.status_code == 400
    details = _details(res)
    assert "date_fin_prevue" in details
    assert "Reprogrammez d'abord le lot parent" in str(details["date_fin_prevue"])


def test_coherence_hierarchique_lot_projet(environnement_chantier):
    """Un lot ne peut jamais dépasser les dates de son projet parent."""
    env = environnement_chantier
    client = env["client_cp"]
    lot = env["lot"]
    motif = env["motif_intemperies"]

    # Le projet finit le 31/12/2026. Tenter de finir le lot le 05/01/2027 doit échouer.
    res = client.post(
        f"/api/v1/lots/{lot.pk}/reprogrammer/",
        {
            "date_fin_prevue": "2027-01-05",
            "motif_id": str(motif.id),
            "justification": "Arrêt technique et intempéries exceptionnelles sur le chantier.",
        },
        format="json",
    )
    assert res.status_code == 400
    details = _details(res)
    assert "date_fin_prevue" in details
    assert "Reprogrammez d'abord le projet" in str(details["date_fin_prevue"])


@patch("apps.projets.services.reprogrammation.notifier_dg_derive_delai.delay")
def test_reprogrammation_valide_sans_alerte_si_derive_inf_ou_egale_30j(mock_celery, environnement_chantier):
    """Report valide avec dérive <= 30 jours : Historique créé, Baseline intacte, pas de Celery."""
    env = environnement_chantier
    client = env["client_cp"]
    p = env["projet"]
    motif = env["motif_intemperies"]

    # Baseline fin : 31/12/2026. Nouvelle fin : 15/01/2027 (+15 jours).
    res = client.post(
        f"/api/v1/projets/{p.pk}/reprogrammer/",
        {
            "date_fin_prevue": "2027-01-15",
            "motif_id": str(motif.id),
            "justification": "Fortes pluies torrentielles ayant inondé les voies d'accès au chantier.",
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["date_fin_prevue"] == "2027-01-15"
    assert res.data["date_fin_baseline"] == "2026-12-31"  # Baseline v0 intacte !
    assert res.data["jours_derive_baseline"] == 15
    assert res.data["alerte_dg_declenchee"] is False

    mock_celery.assert_not_called()

    # Vérification de l'historique en base
    histo = HistoriqueDate.objects.filter(projet=p, type_objet=TypeObjetHistorique.PROJET).first()
    assert histo is not None
    assert histo.valeur_avant == date(2026, 12, 31)
    assert histo.valeur_apres == date(2027, 1, 15)
    assert histo.motif_id == motif.id
    assert histo.auteur_id == env["cp"].id

    # Consultation via endpoint d'historique
    res_h = client.get(f"/api/v1/projets/{p.pk}/historique-dates/")
    assert res_h.status_code == 200
    assert len(res_h.data) == 1
    assert res_h.data[0]["champ"] == "date_fin_prevue"


@patch("apps.projets.services.reprogrammation.notifier_dg_derive_delai.delay")
def test_reprogrammation_avec_alerte_celery_si_derive_sup_30_jours(mock_celery, environnement_chantier):
    """US-033 : Dérive > 30 jours par rapport à la Baseline v0 déclenche une notification Celery au DG."""
    env = environnement_chantier
    client = env["client_cp"]
    p = env["projet"]
    motif = env["motif_intemperies"]

    # Baseline fin : 31/12/2026. Nouvelle fin : 15/02/2027 (+46 jours > 30j).
    res = client.post(
        f"/api/v1/projets/{p.pk}/reprogrammer/",
        {
            "date_fin_prevue": "2027-02-15",
            "motif_id": str(motif.id),
            "justification": "Glissement de terrain majeur nécessitant des travaux confortatifs de consolidation.",
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["jours_derive_baseline"] == 46
    assert res.data["alerte_dg_declenchee"] is True

    # Vérification de l'appel Celery
    mock_celery.assert_called_once()
    _, kwargs = mock_celery.call_args
    assert kwargs["type_objet"] == TypeObjetHistorique.PROJET
    assert kwargs["objet_id"] == str(p.id)
    assert kwargs["jours_derive"] == 46
    assert kwargs["motif_libelle"] == motif.libelle


def test_interdiction_contournement_via_patch_classique(environnement_chantier):
    """Vérifie qu'un utilisateur ne peut pas contourner la règle en patchant directement Projet."""
    env = environnement_chantier
    client = env["client_cp"]
    p = env["projet"]

    res = client.patch(
        f"/api/v1/projets/{p.pk}/",
        {"date_fin_prevue": "2027-03-01"},
        format="json",
    )
    assert res.status_code == 400
    details = _details(res)
    assert "date_fin_prevue" in details
    assert "POST /api/v1/projets/{id}/reprogrammer/" in str(details["date_fin_prevue"])


def test_motifs_dynamiques_liste_et_creation(environnement_chantier):
    """Vérifie la consultation et l'ajout dynamique d'un motif."""
    env = environnement_chantier
    client_admin = env["client_admin"]

    # 1. Lister les motifs
    res_list = client_admin.get("/api/v1/referentiels/motifs-report/")
    assert res_list.status_code == 200
    codes = [m["code"] for m in res_list.data]
    assert "INTEMPERIES" in codes

    # 2. Ajouter un nouveau motif dynamique
    res_post = client_admin.post(
        "/api/v1/referentiels/motifs-report/",
        {
            "code": "APPROVISIONNEMENT",
            "libelle": "Rupture Approvisionnement Matériaux",
            "description": "Retard livraison ciment ou acier.",
            "ordre": 10,
        },
        format="json",
    )
    assert res_post.status_code == 201
    assert res_post.data["code"] == "APPROVISIONNEMENT"

    # Vérification en base
    assert MotifReport.objects.filter(code="APPROVISIONNEMENT").exists()


def test_creation_et_reprogrammation_activite(environnement_chantier):
    """Vérifie le cycle complet d'une activité : création sur lot et reprogrammation."""
    env = environnement_chantier
    client = env["client_cp"]
    lot = env["lot"]
    motif = env["motif_intemperies"]

    # 1. Créer une nouvelle activité
    res_act = client.post(
        f"/api/v1/lots/{lot.pk}/activites/",
        {
            "libelle": "Ferraillage voiles",
            "unite": "KG",
            "quantite_prevue": "1200.000",
            "date_debut_prevue": "2026-10-15",
            "date_fin_prevue": "2026-10-30",
            "ordre": 2,
        },
        format="json",
    )
    assert res_act.status_code == 201, res_act.data
    act_id = res_act.data["id"]
    assert res_act.data["date_debut_baseline"] == "2026-10-15"
    assert res_act.data["date_fin_baseline"] == "2026-10-30"

    # 2. Reprogrammer cette activité
    res_rep = client.post(
        f"/api/v1/activites/{act_id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-11-10",
            "motif_id": str(motif.id),
            "justification": "Retard de livraison des aciers à haute adhérence sur le site.",
        },
        format="json",
    )
    assert res_rep.status_code == 200
    assert res_rep.data["date_fin_prevue"] == "2026-11-10"
    assert res_rep.data["date_fin_baseline"] == "2026-10-30"

    # 3. Consulter l'historique de l'activité
    res_h = client.get(f"/api/v1/activites/{act_id}/historique-dates/")
    assert res_h.status_code == 200
    assert len(res_h.data) == 1
    assert res_h.data[0]["type_objet"] == "ACTIVITE"
