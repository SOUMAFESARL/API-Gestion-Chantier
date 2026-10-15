"""Tests de cohérence des budgets projet / lot / activité et journalisation (B1 - US 3.4, 3.9)."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, RoleProjet
from apps.core.fields import formater_fcfa
from apps.projets.models import Activite, AffectationProjet, Lot, Projet
from apps.projets.serializers import ProjetCreationSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexte(schema_demo):
    dg = Utilisateur.objects.create_user(
        email="dg.budgets@demo.ci",
        password="Test12345!",
        nom="DG",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(dg)
    return client, dg


def creer_fichier_excel(lignes):
    wb = Workbook()
    ws = wb.active
    for ligne in lignes:
        ws.append(ligne)
    flux = BytesIO()
    wb.save(flux)
    wb.close()
    return SimpleUploadedFile(
        "lots.xlsx",
        flux.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def obtenir_details_erreur(response_data):
    if isinstance(response_data, dict) and "erreur" in response_data:
        return response_data["erreur"].get("details", {})
    return response_data


def test_formater_fcfa():
    """Vérifie le formatage des montants en francs avec espaces ordinaires."""
    assert formater_fcfa(1_200_000_000) == "12 000 000 FCFA"
    assert formater_fcfa(0) == "0 FCFA"
    assert formater_fcfa(None) == "0 FCFA"


def test_somme_des_lots_bornee_par_le_projet(contexte):
    """Projet 100 M, lots 60 M + 30 M ; un 3e lot de 20 M -> 400 (reste 10 M) ; 10 M -> 201."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-01",
        nom="Projet B1",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,  # 100 M FCFA
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    Lot.objects.create(
        projet=projet,
        code="L-01",
        libelle="Lot 1",
        budget_initial_montant=60_000_000_00,  # 60 M
    )
    Lot.objects.create(
        projet=projet,
        code="L-02",
        libelle="Lot 2",
        budget_initial_montant=30_000_000_00,  # 30 M
    )

    url = f"/api/v1/projets/{projet.pk}/lots/"
    # Tentative avec 20 M (dépasse de 10 M le plafond)
    rep_refus = client.post(
        url,
        {
            "nom": "Lot 3",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "budget_initial_montant": 20_000_000_00,
        },
        format="json",
    )
    assert rep_refus.status_code == 400, rep_refus.data
    details = obtenir_details_erreur(rep_refus.data)
    assert "budget_initial_montant" in details
    message = str(details["budget_initial_montant"])
    assert "il reste 10 000 000 FCFA" in message
    assert "sur un budget projet de 100 000 000 FCFA" in message

    # Tentative avec 10 M (exactement le reste disponible)
    rep_succes = client.post(
        url,
        {
            "nom": "Lot 3",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "budget_initial_montant": 10_000_000_00,
        },
        format="json",
    )
    assert rep_succes.status_code == 201, rep_succes.data


def test_lot_modifie_compare_aux_autres(contexte):
    """Lots 60 M + 30 M ; passer le second à 40 M -> 200 ; à 41 M -> 400."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-02",
        nom="Projet B1-02",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    Lot.objects.create(
        projet=projet,
        code="L-01",
        libelle="Lot 1",
        budget_initial_montant=60_000_000_00,
    )
    lot2 = Lot.objects.create(
        projet=projet,
        code="L-02",
        libelle="Lot 2",
        budget_initial_montant=30_000_000_00,
    )

    url = f"/api/v1/lots/{lot2.pk}/"
    # Passer à 40 M (total 100 M) -> 200
    rep_ok = client.patch(url, {"budget_initial_montant": 40_000_000_00}, format="json")
    assert rep_ok.status_code == 200, rep_ok.data

    # Passer à 41 M (total 101 M > 100 M) -> 400
    rep_ko = client.patch(url, {"budget_initial_montant": 41_000_000_00}, format="json")
    assert rep_ko.status_code == 400, rep_ko.data
    details = obtenir_details_erreur(rep_ko.data)
    assert "budget_initial_montant" in details


def test_somme_des_activites_bornee_par_le_lot(contexte):
    """Même principe sur un lot de 10 M avec des activités."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-03",
        nom="Projet B1-03",
        ville="Abidjan",
        budget_initial_montant=50_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    lot = Lot.objects.create(
        projet=projet,
        code="L-01",
        libelle="Lot 1",
        budget_initial_montant=10_000_000_00,  # 10 M
    )
    Activite.objects.create(
        lot=lot,
        libelle="Activité 1",
        budget_initial_montant=6_000_000_00,  # 6 M
        quantite_prevue=Decimal("1.000"),
    )

    url = f"/api/v1/lots/{lot.pk}/activites/"
    # 5 M -> 400 (reste 4 M)
    rep_ko = client.post(
        url,
        {"libelle": "Activité 2", "budget_initial_montant": 5_000_000_00},
        format="json",
    )
    assert rep_ko.status_code == 400, rep_ko.data
    details = obtenir_details_erreur(rep_ko.data)
    assert "budget_initial_montant" in details
    assert "il reste 4 000 000 FCFA" in str(details["budget_initial_montant"])

    # 4 M -> 201
    rep_ok = client.post(
        url,
        {"libelle": "Activité 2", "budget_initial_montant": 4_000_000_00},
        format="json",
    )
    assert rep_ok.status_code == 201, rep_ok.data
    act2_id = rep_ok.data["id"]

    # Modification de l'activité 2 à 5 M -> 400
    rep_mod_ko = client.patch(
        f"/api/v1/activites/{act2_id}/",
        {"budget_initial_montant": 5_000_000_00},
        format="json",
    )
    assert rep_mod_ko.status_code == 400, rep_mod_ko.data
    details_mod = obtenir_details_erreur(rep_mod_ko.data)
    assert "budget_initial_montant" in details_mod


def test_projet_ne_descend_pas_sous_ses_lots(contexte):
    """PATCH projet 80 M avec 90 M de lots -> 400 « somme de ses lots (90 000 000 FCFA) »."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-04",
        nom="Projet B1-04",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    Lot.objects.create(
        projet=projet, code="L-01", libelle="Lot 1", budget_initial_montant=60_000_000_00
    )
    Lot.objects.create(
        projet=projet, code="L-02", libelle="Lot 2", budget_initial_montant=30_000_000_00
    )

    url = f"/api/v1/projets/{projet.pk}/"
    rep = client.patch(url, {"budget_initial_montant": 80_000_000_00}, format="json")
    assert rep.status_code == 400, rep.data
    details = obtenir_details_erreur(rep.data)
    assert "budget_initial_montant" in details
    assert "somme de ses lots (90 000 000 FCFA)" in str(details["budget_initial_montant"])


def test_lot_ne_descend_pas_sous_ses_activites(contexte):
    """PATCH lot 8 M avec 9 M d'activités -> 400 « somme de ses activités (9 000 000 FCFA) »."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-05",
        nom="Projet B1-05",
        ville="Abidjan",
        budget_initial_montant=50_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    lot = Lot.objects.create(
        projet=projet, code="L-01", libelle="Lot 1", budget_initial_montant=10_000_000_00
    )
    Activite.objects.create(
        lot=lot, libelle="A1", budget_initial_montant=6_000_000_00, quantite_prevue=Decimal("1")
    )
    Activite.objects.create(
        lot=lot, libelle="A2", budget_initial_montant=3_000_000_00, quantite_prevue=Decimal("1")
    )

    url = f"/api/v1/lots/{lot.pk}/"
    rep = client.patch(url, {"budget_initial_montant": 8_000_000_00}, format="json")
    assert rep.status_code == 400, rep.data
    details = obtenir_details_erreur(rep.data)
    assert "budget_initial_montant" in details
    assert "somme de ses activités (9 000 000 FCFA)" in str(details["budget_initial_montant"])


def test_parent_sans_budget_ne_borne_rien(contexte):
    """Projet sans budget : lots quelconques acceptés.

    Lot sans budget : activités quelconques acceptées.
    """
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-06",
        nom="Projet Sans Budget",
        ville="Abidjan",
        budget_initial_montant=None,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    rep_lot = client.post(
        f"/api/v1/projets/{projet.pk}/lots/",
        {
            "nom": "Lot Libre",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "budget_initial_montant": 500_000_000_00,
        },
        format="json",
    )
    assert rep_lot.status_code == 201, rep_lot.data
    lot_id = rep_lot.data["id"]

    # Mettre le lot sans budget
    client.patch(f"/api/v1/lots/{lot_id}/", {"budget_initial_montant": None}, format="json")

    rep_act = client.post(
        f"/api/v1/lots/{lot_id}/activites/",
        {"libelle": "Activité Libre", "budget_initial_montant": 999_000_000_00},
        format="json",
    )
    assert rep_act.status_code == 201, rep_act.data


def test_enfant_sans_budget_compte_zero(contexte):
    """Un lot sans budget ne change pas la somme des lots."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-07",
        nom="Projet B1-07",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    # Lot 1 sans budget
    Lot.objects.create(
        projet=projet, code="L-01", libelle="Lot Sans Budget", budget_initial_montant=None
    )

    # Lot 2 avec la totalité du budget du projet
    rep_lot2 = client.post(
        f"/api/v1/projets/{projet.pk}/lots/",
        {
            "nom": "Lot Total",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "budget_initial_montant": 100_000_000_00,
        },
        format="json",
    )
    assert rep_lot2.status_code == 201, rep_lot2.data


def test_lots_supprimes_ignores(contexte):
    """Un lot supprimé logiquement ne compte pas dans la somme."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-08",
        nom="Projet B1-08",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    Lot.objects.create(
        projet=projet, code="L-01", libelle="Lot 1", budget_initial_montant=60_000_000_00
    )
    Lot.objects.create(
        projet=projet,
        code="L-02",
        libelle="Lot Supprimé",
        budget_initial_montant=40_000_000_00,
        supprime_le=timezone.now(),
        est_actif=False,
    )

    # 30 M passe car 60 M + 30 M = 90 M <= 100 M (le lot supprimé de 40 M est ignoré)
    rep = client.post(
        f"/api/v1/projets/{projet.pk}/lots/",
        {
            "nom": "Lot 3",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "budget_initial_montant": 30_000_000_00,
        },
        format="json",
    )
    assert rep.status_code == 201, rep.data


def test_import_refuse_en_bloc(contexte):
    """Import Excel dont la somme dépasse -> 400 et aucun lot créé."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-09",
        nom="Projet B1-09",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    Lot.objects.create(
        projet=projet, code="L-01", libelle="Lot 1", budget_initial_montant=80_000_000_00
    )

    # Fichier Excel avec 2 lots de 15 M chacun (30 M au total -> 80 M + 30 M = 110 M > 100 M)
    lignes = [
        ["Nom", "Budget"],
        ["Lot Excel 1", 15_000_000],
        ["Lot Excel 2", 15_000_000],
    ]
    fichier = creer_fichier_excel(lignes)

    url = f"/api/v1/projets/{projet.pk}/lots/import/"
    rep = client.post(url, {"fichier": fichier}, format="multipart")
    assert rep.status_code == 400, rep.data

    # Vérification qu'aucun nouveau lot n'a été créé
    assert Lot.objects.filter(projet=projet, supprime_le__isnull=True).count() == 1


def test_creation_projet_avec_lots(contexte):
    """ProjetCreationSerializer avec un budget et des lots qui le dépassent -> ValidationError."""
    _, dg = contexte
    payload = {
        "nom": "Projet Création Directe",
        "type_projet": "BATIMENT_RESIDENTIEL",
        "ville": "Abidjan",
        "maitre_ouvrage": "MOA Test",
        "budget_initial_montant": 100_000_000_00,  # 100 M
        "lots": [
            {
                "code": "L-01",
                "libelle": "Lot A",
                "mode_execution": "REGIE",
                "type_bordereau": "FORFAIT",
                "budget_initial_montant": 60_000_000_00,
            },
            {
                "code": "L-02",
                "libelle": "Lot B",
                "mode_execution": "REGIE",
                "type_bordereau": "FORFAIT",
                "budget_initial_montant": 50_000_000_00,  # total 110 M
            },
        ],
    }
    factory = APIRequestFactory()
    request = factory.post("/api/v1/projets/", payload, format="json")
    request.user = dg

    serializer = ProjetCreationSerializer(data=payload, context={"request": request})
    assert not serializer.is_valid()
    assert "budget_initial_montant" in serializer.errors


def test_patch_sans_budget_ne_controle_pas(contexte):
    """État incohérent préexistant (forcé en base) ; PATCH du nom -> 200."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-11",
        nom="Projet Incohérent Initial",
        ville="Abidjan",
        budget_initial_montant=50_000_000_00,  # 50 M
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    # On force un lot de 90 M directement en base
    Lot.objects.create(
        projet=projet,
        code="L-01",
        libelle="Lot Géant",
        budget_initial_montant=90_000_000_00,
    )

    url = f"/api/v1/projets/{projet.pk}/"
    rep = client.patch(url, {"nom": "Nouveau Nom Projet"}, format="json")
    assert rep.status_code == 200, rep.data
    projet.refresh_from_db()
    assert projet.nom == "Nouveau Nom Projet"


def test_budget_projet_journalise(contexte):
    """Une ligne JournalAudit avec ancien et nouveau montants ; aucune si inchangé."""
    client, dg = contexte
    projet = Projet.objects.create(
        reference="PRJ-B1-12",
        nom="Projet Audit",
        ville="Abidjan",
        budget_initial_montant=100_000_000_00,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=dg, role_projet=RoleProjet.CHEF_PROJET
    )

    nb_audit_avant = JournalAudit.objects.filter(type_entite="projet", entite_id=projet.pk).count()

    url = f"/api/v1/projets/{projet.pk}/"
    # Modification du budget : 120 M
    rep1 = client.patch(url, {"budget_initial_montant": 120_000_000_00}, format="json")
    assert rep1.status_code == 200, rep1.data

    audits = JournalAudit.objects.filter(type_entite="projet", entite_id=projet.pk)
    assert audits.count() == nb_audit_avant + 1
    derniere_entree = audits.latest("horodatage")
    assert derniere_entree.action == ActionAudit.MODIFICATION
    assert derniere_entree.valeur_avant == {"budget_initial_montant": 100_000_000_00}
    assert derniere_entree.valeur_apres == {"budget_initial_montant": 120_000_000_00}

    # Modification d'un autre champ (ex: description) sans changer le budget
    rep2 = client.patch(url, {"description": "Nouvelle description"}, format="json")
    assert rep2.status_code == 200, rep2.data

    assert (
        JournalAudit.objects.filter(type_entite="projet", entite_id=projet.pk).count()
        == nb_audit_avant + 1
    )
