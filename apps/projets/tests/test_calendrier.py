"""Tests de conformité de l'encadrement calendaire Projet / Lot / Activité (D1 à D7)."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Activite, Lot, MotifReport, Projet
from apps.projets.services.calendrier import MSG_EXIGER_DATES_LOT, MSG_EXIGER_DATES_PROJET
from apps.tiers.models import Tiers

pytestmark = pytest.mark.django_db


@pytest.fixture
def environnement(schema_demo):
    from apps.accounts.services.roles import initialiser_roles_par_defaut

    initialiser_roles_par_defaut()

    dg = Utilisateur.objects.create_user(
        email="dg.calendrier@demo.ci",
        password="Test12345!",
        nom="DG",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        statut=StatutUtilisateur.ACTIF,
    )
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(dg)

    tiers = Tiers.objects.create(raison_sociale="Client BTP Calendrier", type_tiers="ENTREPRISE")

    projet_avec_dates = Projet.objects.create(
        reference="PRJ-CAL-01",
        nom="Chantier Calendrier Validé",
        client=tiers,
        ville="Abidjan",
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
    )

    projet_sans_dates = Projet.objects.create(
        reference="PRJ-CAL-02",
        nom="Chantier Sans Dates",
        client=tiers,
        ville="Abidjan",
        date_debut_prevue=None,
        date_fin_prevue=None,
    )

    motif, _ = MotifReport.objects.get_or_create(
        code="INTEMPERIES",
        defaults={"libelle": "Intempéries exceptionnelles", "est_actif": True},
    )

    return {
        "client": client,
        "dg": dg,
        "tiers": tiers,
        "projet_avec_dates": projet_avec_dates,
        "projet_sans_dates": projet_sans_dates,
        "motif": motif,
    }


def creer_excel_lot(lignes):
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "nom",
            "mode_execution",
            "type_bordereau",
            "budget_fcfa",
            "date_debut_prevue",
            "date_fin_prevue",
        ]
    )
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


def extraire_message(response_data):
    if isinstance(response_data, dict):
        if "erreur" in response_data:
            err = response_data["erreur"]
            return str(err.get("message", "")) + " " + str(err.get("details", ""))
        return str(response_data)
    return str(response_data)


def test_creation_lot_sans_dates_projet_refusee(environnement):
    """D1 : Création de lot refusée si le projet n'a pas de dates."""
    client = environnement["client"]
    p_sans = environnement["projet_sans_dates"]

    res = client.post(
        f"/api/v1/projets/{p_sans.id}/lots/",
        {
            "nom": "Gros œuvre",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
        },
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert MSG_EXIGER_DATES_PROJET in msg


def test_creation_lot_avec_dates_projet_ok(environnement):
    """Création de lot autorisée si le projet a des dates."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]

    res = client.post(
        f"/api/v1/projets/{p_avec.id}/lots/",
        {
            "nom": "Gros œuvre",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "date_debut_prevue": "2026-10-05",
            "date_fin_prevue": "2026-10-20",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["nom"] == "Gros œuvre"


def test_activation_lot_sans_dates_projet_refusee(environnement):
    """D2 : Réactivation d'un lot refusée si le projet n'a pas de dates."""
    client = environnement["client"]
    p_sans = environnement["projet_sans_dates"]
    lot = Lot.objects.create(
        projet=p_sans,
        code="L-01",
        libelle="Lot Inactif",
        est_actif=False,
    )

    res = client.patch(
        f"/api/v1/lots/{lot.id}/activation/",
        {"est_actif": True},
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert MSG_EXIGER_DATES_PROJET in msg


def test_desactivation_lot_sans_dates_projet_permise(environnement):
    """D2 : Désactivation d'un lot toujours permise, même sans dates projet."""
    client = environnement["client"]
    p_sans = environnement["projet_sans_dates"]
    lot = Lot.objects.create(
        projet=p_sans,
        code="L-01",
        libelle="Lot Actif",
        est_actif=True,
    )

    res = client.patch(
        f"/api/v1/lots/{lot.id}/activation/",
        {"est_actif": False},
        format="json",
    )
    assert res.status_code == 200
    lot.refresh_from_db()
    assert lot.est_actif is False


def test_creation_activite_sans_dates_lot_refusee(environnement):
    """D3 : Création d'une activité refusée si le lot n'a pas de dates."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]
    lot_sans = Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Sans Dates",
        date_debut_prevue=None,
        date_fin_prevue=None,
        est_actif=True,
    )

    res = client.post(
        f"/api/v1/lots/{lot_sans.id}/activites/",
        {"libelle": "Terrassement"},
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert MSG_EXIGER_DATES_LOT in msg


def test_activation_activite_sans_dates_lot_refusee(environnement):
    """D3 : Activation d'une activité refusée si le lot n'a pas de dates."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]
    lot_sans = Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Sans Dates",
        date_debut_prevue=None,
        date_fin_prevue=None,
        est_actif=True,
    )
    act = Activite.objects.create(
        lot=lot_sans,
        libelle="Fouille",
        quantite_prevue=Decimal("1.000"),
        est_actif=False,
    )

    res = client.patch(
        f"/api/v1/activites/{act.id}/activation/",
        {"est_actif": True},
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert MSG_EXIGER_DATES_LOT in msg


def test_desactivation_activite_sans_dates_lot_permise(environnement):
    """D3 : Désactivation d'une activité toujours permise."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]
    lot_sans = Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Sans Dates",
        date_debut_prevue=None,
        date_fin_prevue=None,
        est_actif=True,
    )
    act = Activite.objects.create(
        lot=lot_sans,
        libelle="Fouille",
        quantite_prevue=Decimal("1.000"),
        est_actif=True,
    )

    res = client.patch(
        f"/api/v1/activites/{act.id}/activation/",
        {"est_actif": False},
        format="json",
    )
    assert res.status_code == 200
    act.refresh_from_db()
    assert act.est_actif is False


def test_lot_date_hors_bornes_projet_refusee(environnement):
    """D4 : Dates du lot hors bornes du projet refusées."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]  # 2026-10-01 -> 2026-12-31

    # Début avant projet
    res = client.post(
        f"/api/v1/projets/{p_avec.id}/lots/",
        {
            "nom": "Lot Précoce",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "date_debut_prevue": "2026-09-25",
            "date_fin_prevue": "2026-10-25",
        },
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert "Le lot ne peut pas commencer avant le début du projet (01/10/2026)." in msg

    # Fin après projet
    res2 = client.post(
        f"/api/v1/projets/{p_avec.id}/lots/",
        {
            "nom": "Lot Tardif",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
            "date_debut_prevue": "2026-10-05",
            "date_fin_prevue": "2027-01-10",
        },
        format="json",
    )
    assert res2.status_code == 400
    msg2 = extraire_message(res2.data)
    assert "Le lot ne peut pas finir après la fin du projet (31/12/2026)." in msg2


def test_activite_date_hors_bornes_lot_refusee(environnement):
    """D5 : Dates de l'activité hors bornes du lot refusées."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]
    lot = Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Borné",
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 10, 25),
        est_actif=True,
    )

    # Début avant lot
    res = client.post(
        f"/api/v1/lots/{lot.id}/activites/",
        {
            "libelle": "Activité Précoce",
            "date_debut_prevue": "2026-10-02",
            "date_fin_prevue": "2026-10-15",
        },
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert "L'activité ne peut pas commencer avant le début du lot (05/10/2026)." in msg

    # Fin après lot
    res2 = client.post(
        f"/api/v1/lots/{lot.id}/activites/",
        {
            "libelle": "Activité Tardive",
            "date_debut_prevue": "2026-10-10",
            "date_fin_prevue": "2026-10-30",
        },
        format="json",
    )
    assert res2.status_code == 400
    msg2 = extraire_message(res2.data)
    assert "L'activité ne peut pas finir après la fin du lot (25/10/2026)." in msg2


def test_reprogrammation_lot_hors_projet_refusee(environnement):
    """D6 : Reprogrammation d'un lot au-delà des dates projet refusée."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]  # 2026-10-01 -> 2026-12-31
    motif = environnement["motif"]
    lot = Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Reprog",
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 10, 25),
        est_actif=True,
    )

    res = client.post(
        f"/api/v1/lots/{lot.id}/reprogrammer/",
        {
            "date_fin_prevue": "2027-01-15",
            "motif_id": str(motif.id),
            "justification": "Retard important sur approvisionnement des matériaux.",
        },
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    attendu = (
        "Le lot ne peut pas finir après la fin du projet (31/12/2026). "
        "Reprogrammez d'abord le projet."
    )
    assert attendu in msg


def test_reprogrammation_projet_excluant_lot_refusee(environnement):
    """D7 : Reprogrammation d'un projet excluant un lot existant refusée."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]  # 2026-10-01 -> 2026-12-31
    motif = environnement["motif"]
    Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Fin Décembre",
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 12, 28),
        est_actif=True,
    )

    # Réduire la fin du projet au 2026-12-15 (le lot L-01 finit le 28/12)
    res = client.post(
        f"/api/v1/projets/{p_avec.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-12-15",
            "motif_id": str(motif.id),
            "justification": "Avancement accéléré souhaité par la direction générale.",
        },
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert "Le lot L-01 sortirait du calendrier du projet : reprogrammez-le d'abord." in msg


def test_reprogrammation_lot_excluant_activite_refusee(environnement):
    """D7 : Reprogrammation d'un lot excluant une activité existante refusée."""
    client = environnement["client"]
    p_avec = environnement["projet_avec_dates"]
    motif = environnement["motif"]
    lot = Lot.objects.create(
        projet=p_avec,
        code="L-01",
        libelle="Lot Cadré",
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 11, 30),
        est_actif=True,
    )
    Activite.objects.create(
        lot=lot,
        libelle="Bétonnage semelle",
        quantite_prevue=Decimal("1.000"),
        date_debut_prevue=date(2026, 10, 10),
        date_fin_prevue=date(2026, 11, 25),
        est_actif=True,
    )

    # Réduire la fin du lot au 2026-11-15 (l'activité finit le 25/11)
    res = client.post(
        f"/api/v1/lots/{lot.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-11-15",
            "motif_id": str(motif.id),
            "justification": "Réduction de délai demandée pour livraison anticipée.",
        },
        format="json",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    attendu_act = (
        "L'activité Bétonnage semelle sortirait du calendrier du lot : "
        "reprogrammez-la d'abord."
    )
    assert attendu_act in msg


def test_import_excel_sans_dates_projet_refusee(environnement):
    """D1 : Import Excel refusé si le projet n'a pas de dates."""
    client = environnement["client"]
    p_sans = environnement["projet_sans_dates"]

    fichier = creer_excel_lot([["Lot 1", "REGIE", "FORFAIT", None, "2026-10-05", "2026-10-20"]])
    res = client.post(
        f"/api/v1/projets/{p_sans.id}/lots/import/",
        {"fichier": fichier},
        format="multipart",
    )
    assert res.status_code == 400
    msg = extraire_message(res.data)
    assert MSG_EXIGER_DATES_PROJET in msg


def test_creation_projet_avec_lots_sans_dates_projet_refusee(environnement):
    """D1 : Création de projet avec lots refusée si dates projet absentes."""
    dg = environnement["dg"]
    tiers = environnement["tiers"]

    payload = {
        "nom": "Projet Multi-lots Sans Dates",
        "client": tiers.id,
        "ville": "Abidjan",
        "date_debut_prevue": None,
        "date_fin_prevue": None,
        "lots": [
            {
                "libelle": "Terrassement",
                "mode_execution": "REGIE",
                "type_bordereau": "FORFAIT",
            }
        ],
    }
    from rest_framework.test import APIRequestFactory

    from apps.projets.serializers import ProjetCreationSerializer

    factory = APIRequestFactory()
    request = factory.post("/api/v1/projets/", payload, format="json")
    request.user = dg

    serializer = ProjetCreationSerializer(data=payload, context={"request": request})
    assert not serializer.is_valid()
    assert "lots" in serializer.errors
    assert MSG_EXIGER_DATES_PROJET in str(serializer.errors["lots"])


def test_creation_projet_avec_lot_hors_dates_refusee(environnement):
    """D4 : Création de projet avec lot hors bornes refusée."""
    dg = environnement["dg"]
    tiers = environnement["tiers"]

    payload = {
        "nom": "Projet Multi-lots Borné",
        "client": tiers.id,
        "ville": "Abidjan",
        "date_debut_prevue": "2026-10-01",
        "date_fin_prevue": "2026-12-31",
        "lots": [
            {
                "libelle": "Terrassement",
                "mode_execution": "REGIE",
                "type_bordereau": "FORFAIT",
                "date_debut_prevue": "2026-10-05",
                "date_fin_prevue": "2027-01-15",
            }
        ],
    }
    from rest_framework.test import APIRequestFactory

    from apps.projets.serializers import ProjetCreationSerializer

    factory = APIRequestFactory()
    request = factory.post("/api/v1/projets/", payload, format="json")
    request.user = dg

    serializer = ProjetCreationSerializer(data=payload, context={"request": request})
    assert not serializer.is_valid()
    assert "lots" in serializer.errors
    assert "Le lot ne peut pas finir après la fin du projet (31/12/2026)." in str(
        serializer.errors["lots"]
    )
