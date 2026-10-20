"""Tests API pour les alertes de retard (SFD F3 §5.4, §10 et Erratum E-3).

Routes testées :
- GET /api/v1/alertes-retard/
- PATCH /api/v1/alertes-retard/{id}/resoudre/
"""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, RoleProjet, StatutUtilisateur
from apps.projets.models import (
    AffectationProjet,
    AlerteRetard,
    Lot,
    NiveauAlerteRetard,
    Projet,
    StatutAlerteRetard,
)

HOTE_TEST = "demo.localhost"


@pytest.fixture
def api_client():
    """Client API configuré pour le sous-domaine du tenant demo."""
    return APIClient(headers={"host": HOTE_TEST, "x-tenant": "demo"})


@pytest.fixture
def setup_alertes(schema_demo):
    """Crée l'écosystème d'utilisateurs, projets et alertes pour les tests."""
    with schema_context(schema_demo):
        # 1. Utilisateurs
        dg = Utilisateur.objects.create_user(
            email="dg_test_alertes@demo.ci",
            nom="Directeur",
            prenom="General",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )

        do_user = Utilisateur.objects.create_user(
            email="do_test_alertes@demo.ci",
            nom="Directeur",
            prenom="Operations",
            role_global="DO",
            statut=StatutUtilisateur.ACTIF,
        )

        cp = Utilisateur.objects.create_user(
            email="cp_test_alertes@demo.ci",
            nom="Chef",
            prenom="Projet1",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )

        cp_autre = Utilisateur.objects.create_user(
            email="cp_autre_test_alertes@demo.ci",
            nom="Chef",
            prenom="Projet2",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )

        ct = Utilisateur.objects.create_user(
            email="ct_test_alertes@demo.ci",
            nom="Conducteur",
            prenom="Travaux",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )

        # 2. Projets
        projet1 = Projet.objects.create(
            reference="PRJ-AL-P1",
            nom="Chantier Résidence Palmier",
            ville="Abidjan",
            chef_projet=cp,
        )

        projet2 = Projet.objects.create(
            reference="PRJ-AL-P2",
            nom="Chantier Tour Ivoire",
            ville="Bouaké",
            chef_projet=cp_autre,
        )

        # 3. Lot sur projet1
        lot1 = Lot.objects.create(
            projet=projet1,
            code="LOT-01",
            libelle="Gros Œuvre",
        )

        # 4. Alertes
        # Alerte 1 : Ouverte, Élevée, sur lot1, destinataires = [ct, cp]
        alerte_ouverte = AlerteRetard.objects.create(
            projet=projet1,
            lot=lot1,
            niveau=NiveauAlerteRetard.ELEVE,
            delta_pts=Decimal("17.50"),
            indice_sante=None,
            date_detection=date(2026, 10, 15),
            statut=StatutAlerteRetard.OUVERTE,
            causes={"absences": 4, "blocages_ouverts": ["Attente ferraillage"], "incidents": 1},
            actions_recommandees=["Renforcer l'effectif", "Lever les blocages ouverts"],
        )
        alerte_ouverte.destinataires.set([ct, cp])

        # Alerte 2 : Ouverte, Critique, sur projet2 (lot null), destinataire = [cp_autre]
        alerte_critique = AlerteRetard.objects.create(
            projet=projet2,
            lot=None,
            niveau=NiveauAlerteRetard.CRITIQUE,
            delta_pts=None,
            indice_sante=35,
            date_detection=date(2026, 10, 18),
            statut=StatutAlerteRetard.OUVERTE,
            causes={"absences": 0, "blocages_ouverts": ["Arrêt technique"], "incidents": 0},
            actions_recommandees=["Lever les blocages ouverts"],
        )
        alerte_critique.destinataires.set([cp_autre])

        # Alerte 3 : Déjà Résolue, Modérée, sur lot1, sans destinataire spécifique
        alerte_resolue = AlerteRetard.objects.create(
            projet=projet1,
            lot=lot1,
            niveau=NiveauAlerteRetard.MODERE,
            delta_pts=Decimal("6.00"),
            indice_sante=None,
            date_detection=date(2026, 10, 10),
            statut=StatutAlerteRetard.RESOLUE,
            causes={},
            actions_recommandees=["Revoir le planning du lot"],
            commentaire_resolution="Équipes renforcées avec succès la semaine dernière.",
            resolue_par=cp,
            resolue_le=timezone.now(),
        )

        # Alerte 4 : Ignorée, Modérée, sur projet1 (lot null)
        alerte_ignoree = AlerteRetard.objects.create(
            projet=projet1,
            lot=None,
            niveau=NiveauAlerteRetard.MODERE,
            delta_pts=Decimal("5.50"),
            indice_sante=None,
            date_detection=date(2026, 10, 5),
            statut=StatutAlerteRetard.IGNOREE,
            causes={},
            actions_recommandees=[],
            commentaire_resolution="",
        )

        return {
            "dg": dg,
            "do": do_user,
            "cp": cp,
            "cp_autre": cp_autre,
            "ct": ct,
            "projet1": projet1,
            "projet2": projet2,
            "lot1": lot1,
            "alerte_ouverte": alerte_ouverte,
            "alerte_critique": alerte_critique,
            "alerte_resolue": alerte_resolue,
            "alerte_ignoree": alerte_ignoree,
        }


@pytest.mark.django_db
def test_liste_alertes_perimetre_dg_et_do_voient_tout(api_client, setup_alertes):
    """Le DG et le DO voient toutes les alertes de l'entreprise (SFD F3 §5.4 & consigne A3)."""
    dg = setup_alertes["dg"]
    do_user = setup_alertes["do"]

    # 1. Appel par le Directeur Général (DG)
    api_client.force_authenticate(user=dg)
    rep_dg = api_client.get("/api/v1/alertes-retard/")
    assert rep_dg.status_code == status.HTTP_200_OK

    data_dg = rep_dg.json()
    assert "total" in data_dg
    assert "page" in data_dg
    assert "resultats" in data_dg
    assert data_dg["total"] == 4
    assert len(data_dg["resultats"]) == 4

    # Vérification de la structure d'un élément
    item = next(
        a for a in data_dg["resultats"] if a["id"] == str(setup_alertes["alerte_ouverte"].id)
    )
    assert item["projet"]["id"] == str(setup_alertes["projet1"].id)
    assert item["projet"]["reference"] == "PRJ-AL-P1"
    assert item["projet"]["nom"] == "Chantier Résidence Palmier"
    assert item["lot"]["id"] == str(setup_alertes["lot1"].id)
    assert item["lot"]["code"] == "LOT-01"
    assert item["lot"]["libelle"] == "Gros Œuvre"
    assert item["niveau"] == "ELEVE"
    assert item["delta_pts"] == "17.50"
    assert item["indice_sante"] is None
    assert item["date_detection"] == "2026-10-15"
    assert item["statut"] == "OUVERTE"
    assert item["causes"]["absences"] == 4
    assert item["actions_recommandees"] == [
        "Renforcer l'effectif",
        "Lever les blocages ouverts",
    ]
    assert item["commentaire_resolution"] == ""
    assert item["resolue_par"] is None
    assert item["resolue_le"] is None

    # Vérification d'un élément avec lot nul
    item_critique = next(
        a for a in data_dg["resultats"] if a["id"] == str(setup_alertes["alerte_critique"].id)
    )
    assert item_critique["lot"] is None
    assert item_critique["indice_sante"] == 35

    # 2. Appel par le Directeur des Opérations (DO)
    api_client.force_authenticate(user=do_user)
    rep_do = api_client.get("/api/v1/alertes-retard/")
    assert rep_do.status_code == status.HTTP_200_OK
    assert rep_do.json()["total"] == 4


@pytest.mark.django_db
def test_liste_alertes_perimetre_ct_et_cp_destinataires(api_client, setup_alertes):
    """Les autres collaborateurs ne voient que les alertes dont ils sont destinataires."""
    ct = setup_alertes["ct"]
    cp_autre = setup_alertes["cp_autre"]

    # 1. Le CT ne doit voir que l'alerte_ouverte (la seule où il est destinataire)
    api_client.force_authenticate(user=ct)
    rep_ct = api_client.get("/api/v1/alertes-retard/")
    assert rep_ct.status_code == status.HTTP_200_OK
    data_ct = rep_ct.json()
    assert data_ct["total"] == 1
    assert data_ct["resultats"][0]["id"] == str(setup_alertes["alerte_ouverte"].id)

    # 2. Le CP du projet 2 ne doit voir que l'alerte_critique
    api_client.force_authenticate(user=cp_autre)
    rep_cp2 = api_client.get("/api/v1/alertes-retard/")
    assert rep_cp2.status_code == status.HTTP_200_OK
    data_cp2 = rep_cp2.json()
    assert data_cp2["total"] == 1
    assert data_cp2["resultats"][0]["id"] == str(setup_alertes["alerte_critique"].id)


@pytest.mark.django_db
def test_liste_alertes_filtres(api_client, setup_alertes):
    """Vérifie le fonctionnement des filtres niveau, projet et statut."""
    dg = setup_alertes["dg"]
    projet1 = setup_alertes["projet1"]
    api_client.force_authenticate(user=dg)

    # Filtre par niveau
    rep_niveau = api_client.get("/api/v1/alertes-retard/?niveau=CRITIQUE")
    assert rep_niveau.status_code == status.HTTP_200_OK
    assert rep_niveau.json()["total"] == 1
    assert rep_niveau.json()["resultats"][0]["niveau"] == "CRITIQUE"

    # Filtre par projet
    rep_projet = api_client.get(f"/api/v1/alertes-retard/?projet={projet1.id}")
    assert rep_projet.status_code == status.HTTP_200_OK
    assert rep_projet.json()["total"] == 3
    for a in rep_projet.json()["resultats"]:
        assert a["projet"]["id"] == str(projet1.id)

    # Filtre par statut
    rep_statut = api_client.get("/api/v1/alertes-retard/?statut=OUVERTE")
    assert rep_statut.status_code == status.HTTP_200_OK
    assert rep_statut.json()["total"] == 2
    for a in rep_statut.json()["resultats"]:
        assert a["statut"] == "OUVERTE"

    rep_resolue = api_client.get("/api/v1/alertes-retard/?statut=RESOLUE")
    assert rep_resolue.status_code == status.HTTP_200_OK
    assert rep_resolue.json()["total"] == 1
    assert rep_resolue.json()["resultats"][0]["statut"] == "RESOLUE"

    # Combinaison de filtres
    rep_combo = api_client.get(
        f"/api/v1/alertes-retard/?niveau=ELEVE&projet={projet1.id}&statut=OUVERTE"
    )
    assert rep_combo.status_code == status.HTTP_200_OK
    assert rep_combo.json()["total"] == 1
    assert rep_combo.json()["resultats"][0]["id"] == str(setup_alertes["alerte_ouverte"].id)


@pytest.mark.django_db
def test_resolution_par_chef_projet_succes(api_client, setup_alertes):
    """Le Chef de Projet (CP) assigné au chantier peut résoudre une alerte (200)."""
    cp = setup_alertes["cp"]
    alerte = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=cp)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"
    commentaire = (
        "Équipes renforcées avec 3 ouvriers supplémentaires sur le gros œuvre."
    )
    corps = {"commentaire_resolution": commentaire}

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_200_OK

    data = rep.json()
    assert data["id"] == str(alerte.id)
    assert data["statut"] == "RESOLUE"
    assert data["commentaire_resolution"] == commentaire
    assert data["resolue_par"] == "Projet1 Chef"
    assert data["resolue_le"] is not None

    # Vérification en base de données
    with schema_context("demo"):
        alerte.refresh_from_db()
        assert alerte.statut == StatutAlerteRetard.RESOLUE
        assert alerte.resolue_par == cp
        assert alerte.resolue_le is not None
        assert alerte.commentaire_resolution == commentaire


@pytest.mark.django_db
def test_resolution_par_cp_affecte_succes(api_client, setup_alertes):
    """Un utilisateur affecté au projet avec le rôle CP peut résoudre l'alerte (200)."""
    projet1 = setup_alertes["projet1"]
    alerte = setup_alertes["alerte_ouverte"]

    with schema_context("demo"):
        cp_affecte = Utilisateur.objects.create_user(
            email="cp_affecte@demo.ci",
            nom="Koné",
            prenom="Ibrahim",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )
        AffectationProjet.objects.create(
            projet=projet1,
            utilisateur=cp_affecte,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        )

    api_client.force_authenticate(user=cp_affecte)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"
    commentaire = (
        "Réorganisation des postes de travail et planification validée."
    )
    corps = {"commentaire_resolution": commentaire}

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.json()["statut"] == "RESOLUE"
    assert rep.json()["resolue_par"] == "Ibrahim Koné"


@pytest.mark.django_db
def test_resolution_par_do_succes(api_client, setup_alertes):
    """Un DO peut résoudre n'importe quelle alerte de l'entreprise (200)."""
    do_user = setup_alertes["do"]
    alerte = setup_alertes["alerte_critique"]

    api_client.force_authenticate(user=do_user)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"
    commentaire = (
        "Déblocage budgétaire et réapprovisionnement prioritaire validés."
    )
    corps = {"commentaire_resolution": commentaire}

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert data["statut"] == "RESOLUE"
    assert data["commentaire_resolution"] == commentaire
    assert data["resolue_par"] == "Operations Directeur"


@pytest.mark.django_db
def test_resolution_par_dg_refusee(api_client, setup_alertes):
    """Le Directeur Général (DG) n'a PAS le droit de résoudre les alertes (SFD §3, 403)."""
    dg = setup_alertes["dg"]
    alerte = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=dg)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"
    corps = {
        "commentaire_resolution": "Tentative de résolution par le Directeur Général."
    }

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN

    data = rep.json()
    assert "erreur" in data
    assert data["erreur"]["code"] == "acces_refuse"
    assert "Directeur Général" in data["erreur"]["message"]

    # L'alerte est restée OUVERTE
    with schema_context("demo"):
        alerte.refresh_from_db()
        assert alerte.statut == StatutAlerteRetard.OUVERTE
        assert alerte.resolue_par is None


@pytest.mark.django_db
def test_resolution_par_ct_refusee(api_client, setup_alertes):
    """Un Conducteur de Travaux (CT) ne peut PAS résoudre une alerte (SFD §3, 403)."""
    ct = setup_alertes["ct"]
    alerte = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=ct)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"
    corps = {
        "commentaire_resolution": "Tentative de résolution par le Conducteur de Travaux."
    }

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN

    data = rep.json()
    assert "erreur" in data
    assert data["erreur"]["code"] == "acces_refuse"
    assert (
        "Chef de Projet" in data["erreur"]["message"]
        or "Directeur des Opérations" in data["erreur"]["message"]
    )


@pytest.mark.django_db
def test_resolution_par_cp_autre_projet_refusee(api_client, setup_alertes):
    """Le CP d'un autre projet ne peut pas résoudre les alertes d'un chantier tiers (403)."""
    cp_autre = setup_alertes["cp_autre"]
    alerte_p1 = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=cp_autre)
    url = f"/api/v1/alertes-retard/{alerte_p1.id}/resoudre/"
    corps = {
        "commentaire_resolution": "Tentative de résolution d'un projet non affecté."
    }

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_403_FORBIDDEN
    assert rep.json()["erreur"]["code"] == "acces_refuse"


@pytest.mark.django_db
def test_resolution_commentaire_court_erreur_400(api_client, setup_alertes):
    """Un commentaire de moins de 10 caractères renvoie 400 validation."""
    cp = setup_alertes["cp"]
    alerte = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=cp)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"

    # Moins de 10 caractères
    rep = api_client.patch(url, {"commentaire_resolution": "TropCourt"}, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST

    data = rep.json()
    assert data["erreur"]["code"] == "validation"
    assert "commentaire_resolution" in data["erreur"]["details"]


@pytest.mark.django_db
def test_resolution_commentaire_manquant_erreur_400(api_client, setup_alertes):
    """Un corps sans commentaire_resolution renvoie 400 validation."""
    cp = setup_alertes["cp"]
    alerte = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=cp)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"

    rep = api_client.patch(url, {}, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST

    data = rep.json()
    assert data["erreur"]["code"] == "validation"
    assert "commentaire_resolution" in data["erreur"]["details"]


@pytest.mark.django_db
def test_resolution_alerte_deja_resolue_erreur_422(api_client, setup_alertes):
    """Une alerte déjà RESOLUE renvoie ErreurMetier (422)."""
    cp = setup_alertes["cp"]
    alerte_resolue = setup_alertes["alerte_resolue"]

    api_client.force_authenticate(user=cp)
    url = f"/api/v1/alertes-retard/{alerte_resolue.id}/resoudre/"
    corps = {
        "commentaire_resolution": "Tentative de re-résolution d'une alerte déjà clôturée."
    }

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    data = rep.json()
    assert data["erreur"]["code"] == "regle_metier"
    assert "déjà résolue" in data["erreur"]["message"]


@pytest.mark.django_db
def test_resolution_alerte_deja_ignoree_erreur_422(api_client, setup_alertes):
    """Une alerte déjà IGNOREE renvoie ErreurMetier (422)."""
    cp = setup_alertes["cp"]
    alerte_ignoree = setup_alertes["alerte_ignoree"]

    api_client.force_authenticate(user=cp)
    url = f"/api/v1/alertes-retard/{alerte_ignoree.id}/resoudre/"
    corps = {
        "commentaire_resolution": "Tentative de résolution d'une alerte ignorée."
    }

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    data = rep.json()
    assert data["erreur"]["code"] == "regle_metier"
    assert "déjà résolue ou ignorée" in data["erreur"]["message"]


@pytest.mark.django_db
def test_resolution_trace_audit(api_client, setup_alertes):
    """La résolution génère une trace d'audit conforme dans JournalAudit."""
    cp = setup_alertes["cp"]
    alerte = setup_alertes["alerte_ouverte"]

    api_client.force_authenticate(user=cp)
    url = f"/api/v1/alertes-retard/{alerte.id}/resoudre/"
    commentaire = (
        "Traitement de l'alerte et mise en place d'un calendrier de rattrapage."
    )
    corps = {"commentaire_resolution": commentaire}

    rep = api_client.patch(url, corps, format="json")
    assert rep.status_code == status.HTTP_200_OK

    with schema_context("demo"):
        audit_qs = JournalAudit.objects.filter(
            entite_id=alerte.id,
            type_entite="AlerteRetard",
            action=ActionAudit.MODIFICATION,
        )
        assert audit_qs.count() == 1
        audit_entry = audit_qs.first()

        assert audit_entry is not None
        assert audit_entry.utilisateur_id == cp.id
        assert audit_entry.valeur_avant == {"statut": "OUVERTE"}
        assert audit_entry.valeur_apres["statut"] == "RESOLUE"
        assert audit_entry.valeur_apres["commentaire_resolution"] == commentaire
        assert audit_entry.valeur_apres["resolue_par_id"] == str(cp.id)
        assert "resolue_le" in audit_entry.valeur_apres


@pytest.mark.django_db
def test_suppression_logique_projet_masque_alertes_et_empeche_resolution(
    api_client, setup_alertes
):
    """Alertes d'un projet supprimé logiquement : absentes de la liste, 404 à la résolution."""
    dg = setup_alertes["dg"]
    do_user = setup_alertes["do"]
    projet2 = setup_alertes["projet2"]
    alerte_critique = setup_alertes["alerte_critique"]

    # Suppression logique du projet 2
    with schema_context("demo"):
        projet2.supprime_le = timezone.now()
        projet2.save(update_fields=["supprime_le"])

    # 1. Le DG ne voit plus que 3 alertes (l'alerte critique sur projet 2 est masquée)
    api_client.force_authenticate(user=dg)
    rep_dg = api_client.get("/api/v1/alertes-retard/")
    assert rep_dg.status_code == status.HTTP_200_OK
    assert rep_dg.json()["total"] == 3
    ids = [a["id"] for a in rep_dg.json()["resultats"]]
    assert str(alerte_critique.id) not in ids

    # 2. Le DO tente de résoudre l'alerte du projet supprimé -> 404
    api_client.force_authenticate(user=do_user)
    url = f"/api/v1/alertes-retard/{alerte_critique.id}/resoudre/"
    corps = {
        "commentaire_resolution": "Tentative de résolution sur un chantier supprimé."
    }
    rep_do = api_client.patch(url, corps, format="json")
    assert rep_do.status_code == status.HTTP_404_NOT_FOUND
