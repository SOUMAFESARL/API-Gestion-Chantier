"""Tests du Journal d'Audit des Reports de dates (RG-07, RG-11).

Vérifie :
1. Calcul automatique et persistance immuable de l'écart en jours (ecart_jours).
2. Immuabilité stricte au niveau Python (save() et delete() refusés avec ValidationError).
3. Immuabilité physique au niveau PostgreSQL (Trigger SQL interdisant UPDATE et DELETE).
4. Consultation consolidée par projet (/api/v1/projets/{id}/journal-reports/) agrégeant projet, lots et activités.
5. Consultation globale transverse (/api/v1/projets/journal-reports/) avec filtres (motif, auteur, écart, type_objet).
6. Respect des permissions RBAC et cloisonnement multi-tenant.
"""

from datetime import date
from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError
from django.db import connection, DatabaseError, transaction
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
def environnement_audit(schema_demo):
    """Initialise un environnement complet avec DG, CP, Collaborateur externe, projet, lots, activités et motifs."""
    from apps.accounts.services.roles import initialiser_roles_par_defaut
    initialiser_roles_par_defaut()

    def user(nom, role):
        return Utilisateur.objects.create_user(
            email=f"{nom}.audit@demo.ci",
            password="TestAudit12345!",
            nom=nom,
            role_global=role,
            statut=StatutUtilisateur.ACTIF,
        )

    dg = user("dg", RoleGlobal.DIRECTEUR_GENERAL)
    admin = user("admin", RoleGlobal.ADMIN)
    cp = user("cp", RoleGlobal.CHEF_PROJET)
    autre_cp = user("autre_cp", RoleGlobal.CHEF_PROJET)

    tiers = Tiers.objects.create(raison_sociale="Maître d'Ouvrage CI", type_tiers="ENTREPRISE")

    projet = Projet.objects.create(
        reference="PRJ-AUDIT-01",
        nom="Chantier Tour Panoramique",
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
        code="LOT-STRUCTURE",
        libelle="Structure Béton",
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 12, 15),
    )

    activite = Activite.objects.create(
        lot=lot,
        libelle="Élévation Poteaux R+1",
        unite=UniteMesure.METRE_CUBE,
        quantite_prevue=Decimal("30.000"),
        date_debut_prevue=date(2026, 10, 10),
        date_fin_prevue=date(2026, 10, 25),
    )

    motif_intemperies = MotifReport.objects.filter(code="INTEMPERIES").first()
    if not motif_intemperies:
        motif_intemperies = MotifReport.objects.create(
            code="INTEMPERIES",
            libelle="Intempéries",
            ordre=1,
            est_actif=True,
        )

    motif_client = MotifReport.objects.filter(code="CLIENT").first()
    if not motif_client:
        motif_client = MotifReport.objects.create(
            code="CLIENT",
            libelle="Modification Client",
            ordre=2,
            est_actif=True,
        )

    client_cp = APIClient(headers={"host": "demo.localhost"})
    client_cp.force_authenticate(cp)

    client_autre_cp = APIClient(headers={"host": "demo.localhost"})
    client_autre_cp.force_authenticate(autre_cp)

    client_dg = APIClient(headers={"host": "demo.localhost"})
    client_dg.force_authenticate(dg)

    client_admin = APIClient(headers={"host": "demo.localhost"})
    client_admin.force_authenticate(admin)

    return {
        "dg": dg,
        "admin": admin,
        "cp": cp,
        "autre_cp": autre_cp,
        "projet": projet,
        "lot": lot,
        "activite": activite,
        "motif_intemperies": motif_intemperies,
        "motif_client": motif_client,
        "client_cp": client_cp,
        "client_autre_cp": client_autre_cp,
        "client_dg": client_dg,
        "client_admin": client_admin,
    }


def test_calcul_et_persistance_ecart_jours(environnement_audit):
    """Vérifie le calcul automatique et persistant de ecart_jours lors de reports."""
    env = environnement_audit
    client = env["client_cp"]
    act = env["activite"]
    motif = env["motif_intemperies"]

    # Reprogrammer l'activité de 10 jours de plus (du 25/10 au 04/11)
    res = client.post(
        f"/api/v1/activites/{act.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-11-04",
            "motif_id": str(motif.id),
            "justification": "Fortes pluies torrentielles ayant inondé le niveau inférieur.",
        },
        format="json",
    )
    assert res.status_code == 200

    # Vérification en base de données
    h = HistoriqueDate.objects.filter(activite=act).first()
    assert h is not None
    assert h.valeur_avant == date(2026, 10, 25)
    assert h.valeur_apres == date(2026, 11, 4)
    assert h.ecart_jours == 10
    assert h.motif == motif
    assert h.auteur == env["cp"]


def test_immuabilite_python_save_et_delete(environnement_audit):
    """Vérifie qu'au niveau applicatif Python, save() et delete() refusent toute modification d'audit."""
    env = environnement_audit
    client = env["client_cp"]
    act = env["activite"]
    motif = env["motif_intemperies"]

    client.post(
        f"/api/v1/activites/{act.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-11-04",
            "motif_id": str(motif.id),
            "justification": "Fortes pluies torrentielles ayant inondé le niveau inférieur.",
        },
        format="json",
    )

    h = HistoriqueDate.objects.filter(activite=act).first()
    assert h is not None

    # Tentative d'altération de la justification
    h.justification = "Tentative frauduleuse de modification de la justification"
    with pytest.raises(ValidationError) as exc_save:
        h.save()
    assert "immuable" in str(exc_save.value).lower()

    # Tentative de suppression
    with pytest.raises(ValidationError) as exc_del:
        h.delete()
    assert "supprimée" in str(exc_del.value).lower()


def test_immuabilite_postgresql_trigger(environnement_audit):
    """Vérifie qu'au niveau moteur PostgreSQL, le trigger bloque UPDATE et DELETE."""
    env = environnement_audit
    client = env["client_cp"]
    act = env["activite"]
    motif = env["motif_intemperies"]

    client.post(
        f"/api/v1/activites/{act.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-11-04",
            "motif_id": str(motif.id),
            "justification": "Fortes pluies torrentielles ayant inondé le niveau inférieur.",
        },
        format="json",
    )

    h = HistoriqueDate.objects.filter(activite=act).first()
    assert h is not None

    # Test UPDATE brut en SQL
    with pytest.raises(DatabaseError) as exc_sql_update:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE historique_date SET justification = %s WHERE id = %s",
                    ["Altération directe SQL", str(h.id)],
                )
    assert "immuable" in str(exc_sql_update.value).lower()

    # Test DELETE brut en SQL
    with pytest.raises(DatabaseError) as exc_sql_delete:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM historique_date WHERE id = %s",
                    [str(h.id)],
                )
    assert "immuable" in str(exc_sql_delete.value).lower()


def test_journal_reports_consolide_projet(environnement_audit):
    """Vérifie que le journal consolidé d'un projet retourne tous les reports du projet, de ses lots et activités."""
    env = environnement_audit
    client_cp = env["client_cp"]
    projet = env["projet"]
    lot = env["lot"]
    act = env["activite"]
    motif1 = env["motif_intemperies"]
    motif2 = env["motif_client"]

    # 1. Report de l'activité (+5 jours)
    res_act = client_cp.post(
        f"/api/v1/activites/{act.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-10-30",
            "motif_id": str(motif1.id),
            "justification": "Pluies intenses retardant les travaux de ferraillage et coulage.",
        },
        format="json",
    )
    assert res_act.status_code == 200

    # 2. Report du lot (+10 jours)
    res_lot = client_cp.post(
        f"/api/v1/lots/{lot.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-12-25",
            "motif_id": str(motif2.id),
            "justification": "Demande de modifications architecturales par le client sur les plans.",
        },
        format="json",
    )
    assert res_lot.status_code == 200

    # 3. Report du projet (+15 jours)
    res_prj = client_cp.post(
        f"/api/v1/projets/{projet.id}/reprogrammer/",
        {
            "date_fin_prevue": "2027-01-15",
            "motif_id": str(motif1.id),
            "justification": "Glissement global dû à la saison des pluies exceptionnelle constatée.",
        },
        format="json",
    )
    assert res_prj.status_code == 200

    # 4. Consultation du journal consolidé du projet
    res_journal = client_cp.get(f"/api/v1/projets/{projet.id}/journal-reports/")
    assert res_journal.status_code == 200
    data = res_journal.data
    assert "resultats" in data
    results = data["resultats"]
    assert len(results) == 3

    # Vérification des métadonnées enrichies
    types_presents = {item["type_objet"] for item in results}
    assert types_presents == {"PROJET", "LOT", "ACTIVITE"}

    for item in results:
        assert "ecart_jours" in item
        assert "valeur_avant" in item
        assert "valeur_apres" in item
        assert "auteur_nom" in item
        assert "objet_libelle" in item
        assert item["projet_id"] == str(projet.id)
        assert item["projet_nom"] == projet.nom


def test_journal_reports_global_et_filtres(environnement_audit):
    """Vérifie la consultation globale du journal des reports et le fonctionnement des filtres multi-critères."""
    env = environnement_audit
    client_cp = env["client_cp"]
    client_dg = env["client_dg"]
    projet = env["projet"]
    lot = env["lot"]
    act = env["activite"]
    motif1 = env["motif_intemperies"]
    motif2 = env["motif_client"]

    # Créer deux reports
    client_cp.post(
        f"/api/v1/activites/{act.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-10-30",
            "motif_id": str(motif1.id),
            "justification": "Pluies intenses retardant les travaux de ferraillage et coulage.",
        },
        format="json",
    )
    client_cp.post(
        f"/api/v1/lots/{lot.id}/reprogrammer/",
        {
            "date_fin_prevue": "2026-12-25",
            "motif_id": str(motif2.id),
            "justification": "Demande de modifications architecturales par le client sur les plans.",
        },
        format="json",
    )

    # 1. DG consulte le journal global sans filtre
    res_all = client_dg.get("/api/v1/projets/journal-reports/")
    assert res_all.status_code == 200
    assert len(res_all.data["resultats"]) == 2

    # 2. Filtre par motif CLIENT
    res_f_motif = client_dg.get(f"/api/v1/projets/journal-reports/?motif_id={motif2.id}")
    assert res_f_motif.status_code == 200
    assert len(res_f_motif.data["resultats"]) == 1
    assert res_f_motif.data["resultats"][0]["type_objet"] == "LOT"

    # 3. Filtre par type_objet ACTIVITE
    res_f_type = client_dg.get("/api/v1/projets/journal-reports/?type_objet=ACTIVITE")
    assert res_f_type.status_code == 200
    assert len(res_f_type.data["resultats"]) == 1
    assert res_f_type.data["resultats"][0]["type_objet"] == "ACTIVITE"

    # 4. Filtre par ecart_min
    # Lot a glissé du 15/12 au 25/12 -> 10 jours
    # Activité a glissé du 25/10 au 30/10 -> 5 jours
    res_f_ecart = client_dg.get("/api/v1/projets/journal-reports/?ecart_min=8")
    assert res_f_ecart.status_code == 200
    assert len(res_f_ecart.data["resultats"]) == 1
    assert res_f_ecart.data["resultats"][0]["ecart_jours"] == 10


def test_permissions_rbac_journal_reports(environnement_audit):
    """Vérifie que seuls les utilisateurs autorisés accèdent au journal consolidé et global."""
    env = environnement_audit
    client_autre_cp = env["client_autre_cp"]
    client_dg = env["client_dg"]
    projet = env["projet"]

    # Un CP non affecté au projet tente d'accéder au journal consolidé du projet -> 403 Forbidden
    res_forbidden = client_autre_cp.get(f"/api/v1/projets/{projet.id}/journal-reports/")
    assert res_forbidden.status_code == 403

    # Le DG (directeur général) a accès au journal consolidé même sans affectation explicite
    res_dg = client_dg.get(f"/api/v1/projets/{projet.id}/journal-reports/")
    assert res_dg.status_code == 200
