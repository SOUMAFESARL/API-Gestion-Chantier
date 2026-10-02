"""Tests automatisés pour l'API du Journal de Chantier (Sprint 2 / Module 2).

Vérifie l'enregistrement, la modification, la lecture et le cycle de vie des
rapports de chantier (US-038, US-042, US-043, RG-02, RG-03, Socle Commun §3.1).
"""

from datetime import date, timedelta

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.chantier.models import RapportJournalier
from apps.core.enums import (
    Meteo,
    ModeExecution,
    RoleGlobal,
    RoleProjet,
    StatutProjet,
    StatutRapport,
    StatutUtilisateur,
    TypeTiers,
)
from apps.core.exceptions import ErreurMetier
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def setup_chantier(db):
    """Prépare les utilisateurs, un projet et un lot de test dans le schéma tenant."""
    with schema_context(SCHEMA):
        # Initialisation des rôles RBAC par défaut
        initialiser_roles_par_defaut()

        # Nettoyage préalable
        RapportJournalier.tous_objets.all().delete()
        Lot.objects.all().delete()
        AffectationProjet.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(
            email__in=[
                "dg.chantier@demo.ci",
                "cc.chantier@demo.ci",
                "ct.chantier@demo.ci",
            ]
        ).delete()

        # Utilisateur DG (Owner)
        dg = Utilisateur.objects.create_user(
            email="dg.chantier@demo.ci",
            password=MOT_DE_PASSE,
            nom="DG",
            prenom="Chantier",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )

        # Conducteur de Travaux (CT)
        ct = Utilisateur.objects.create_user(
            email="ct.chantier@demo.ci",
            password=MOT_DE_PASSE,
            nom="Konan",
            prenom="Conducteur",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )

        # Chef de Chantier (CC)
        cc = Utilisateur.objects.create_user(
            email="cc.chantier@demo.ci",
            password=MOT_DE_PASSE,
            nom="Bamba",
            prenom="Chef",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )

        # Client MOA
        client_tiers = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="Promotion Immobilière CI",
            telephone="+2250708091011",
        )

        # Projet
        projet = Projet.objects.create(
            reference="PRJ-TEST-001",
            nom="Résidence Les Palmiers",
            client=client_tiers,
            chef_projet=ct,
            date_debut_prevue=date.today() - timedelta(days=30),
            date_fin_prevue=date.today() + timedelta(days=180),
            statut=StatutProjet.EN_COURS,
        )

        # Affectations
        AffectationProjet.objects.create(
            projet=projet,
            utilisateur=ct,
            role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
            est_actif=True,
        )
        AffectationProjet.objects.create(
            projet=projet,
            utilisateur=cc,
            role_projet=RoleProjet.CHEF_CHANTIER,
            est_actif=True,
        )

        # Lot
        lot = Lot.objects.create(
            projet=projet,
            code="LOT-01",
            libelle="Gros Œuvre & Maçonnerie",
            mode_execution=ModeExecution.REGIE,
            premier_rapport_soumis=False,
        )

        yield {
            "dg": dg,
            "ct": ct,
            "cc": cc,
            "projet": projet,
            "lot": lot,
        }

        # Nettoyage après test
        RapportJournalier.tous_objets.all().delete()
        Lot.objects.all().delete()
        AffectationProjet.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(
            email__in=[
                "dg.chantier@demo.ci",
                "cc.chantier@demo.ci",
                "ct.chantier@demo.ci",
            ]
        ).delete()


def authentifier(client, utilisateur):
    rep = client.post(
        "/api/v1/auth/token/",
        {"email": utilisateur.email, "mot_de_passe": MOT_DE_PASSE, "origine": "WEB"},
        format="json",
    )
    token = rep.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ==============================================================================
# TESTS ENREGISTREMENT & CREATION (US-038)
# ==============================================================================


@pytest.mark.django_db
def test_creer_rapport_nominal_brouillon(client_tenant, setup_chantier):
    """Enregistre un rapport en BROUILLON avec calcul automatique de l'effectif."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]
    cl = authentifier(client_tenant, cc)

    payload = {
        "projet_id": str(projet.id),
        "lot_id": str(lot.id),
        "date_rapport": str(date.today()),
        "meteo": Meteo.ENSOLEILLE,
        "effectif_regie": 8,
        "effectif_tacherons": 4,
        "observations": "Début coulage de la dalle niveau 1.",
        "statut": StatutRapport.BROUILLON,
    }

    rep = cl.post("/api/v1/rapports/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    data = rep.data
    assert data["statut"] == StatutRapport.BROUILLON
    assert data["effectif_regie"] == 8
    assert data["effectif_tacherons"] == 4
    # Calcul automatique 8 + 4 = 12
    assert data["effectif_present"] == 12
    assert data["observations"] == "Début coulage de la dalle niveau 1."

    # En mode brouillon, le lot ne doit pas encore être verrouillé
    with schema_context(SCHEMA):
        lot.refresh_from_db()
        assert lot.premier_rapport_soumis is False


@pytest.mark.django_db
def test_creer_rapport_soumis_et_verrouillage_lot(client_tenant, setup_chantier):
    """Un rapport créé directement en SOUMIS verrouille le mode d'exécution du lot (RG-03)."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]
    cl = authentifier(client_tenant, cc)

    payload = {
        "projet_id": str(projet.id),
        "lot_id": str(lot.id),
        "date_rapport": str(date.today()),
        "meteo": Meteo.PLUIE,
        "effectif_regie": 5,
        "effectif_tacherons": 0,
        "observations": "Pluie matinale, reprise des travaux à 11h.",
        "statut": StatutRapport.SOUMIS,
    }

    rep = cl.post("/api/v1/rapports/", payload, format="json")
    assert rep.status_code == status.HTTP_201_CREATED
    assert rep.data["statut"] == StatutRapport.SOUMIS
    assert rep.data["soumis_le"] is not None

    with schema_context(SCHEMA):
        lot.refresh_from_db()
        assert lot.premier_rapport_soumis is True


@pytest.mark.django_db
def test_conflit_409_meme_lot_et_date(client_tenant, setup_chantier):
    """Tentative d'enregistrer deux rapports pour le même lot à la même date renvoie 409 Conflict (RG-02 / US-038)."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]
    cl = authentifier(client_tenant, cc)

    payload = {
        "projet_id": str(projet.id),
        "lot_id": str(lot.id),
        "date_rapport": str(date.today()),
        "statut": StatutRapport.BROUILLON,
    }

    rep1 = cl.post("/api/v1/rapports/", payload, format="json")
    assert rep1.status_code == status.HTTP_201_CREATED

    rep2 = cl.post("/api/v1/rapports/", payload, format="json")
    assert rep2.status_code == status.HTTP_409_CONFLICT
    assert rep2.data["erreur"]["code"] == "rapport_deja_existant"


# ==============================================================================
# TESTS MODIFICATION & AUTO-SAVE (US-038)
# ==============================================================================


@pytest.mark.django_db
def test_modifier_rapport_brouillon_patch(client_tenant, setup_chantier):
    """Mise à jour partielle (auto-save ou édition) sur un rapport BROUILLON."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]
    cl = authentifier(client_tenant, cc)

    # 1. Création initiale
    rep_create = cl.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(projet.id),
            "lot_id": str(lot.id),
            "date_rapport": str(date.today()),
            "statut": StatutRapport.BROUILLON,
            "effectif_regie": 3,
        },
        format="json",
    )
    rapport_id = rep_create.data["id"]

    # 2. Patch / auto-save
    rep_patch = cl.patch(
        f"/api/v1/rapports/{rapport_id}/",
        {
            "effectif_regie": 6,
            "observations": "Mise à jour automatique 30s.",
        },
        format="json",
    )
    assert rep_patch.status_code == status.HTTP_200_OK
    assert rep_patch.data["effectif_regie"] == 6
    assert rep_patch.data["effectif_present"] == 6
    assert rep_patch.data["observations"] == "Mise à jour automatique 30s."


@pytest.mark.django_db
def test_interdiction_modifier_rapport_approuve(client_tenant, setup_chantier):
    """Un rapport approuvé est verrouillé et ne peut plus être modifié (US-042 / MLD §6.7)."""
    cc = setup_chantier["cc"]
    ct = setup_chantier["ct"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]

    # Création puis validation
    cl_cc = authentifier(client_tenant, cc)
    rep_create = cl_cc.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(projet.id),
            "lot_id": str(lot.id),
            "date_rapport": str(date.today()),
            "statut": StatutRapport.SOUMIS,
        },
        format="json",
    )
    rapport_id = rep_create.data["id"]

    # Le CT valide le rapport
    cl_ct = APIClient(headers={"host": HOTE})
    cl_ct = authentifier(cl_ct, ct)
    rep_val = cl_ct.post(
        f"/api/v1/rapports/{rapport_id}/valider/",
        {"commentaire": "Travaux conformes aux plans"},
        format="json",
    )
    assert rep_val.status_code == status.HTTP_200_OK
    assert rep_val.data["statut"] == StatutRapport.APPROUVE

    # Tentative de modification par le CC rejetée en 422
    rep_modif = cl_cc.patch(
        f"/api/v1/rapports/{rapport_id}/",
        {"observations": "Modification illégale"},
        format="json",
    )
    assert rep_modif.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert rep_modif.data["erreur"]["code"] == "rapport_non_modifiable"


# ==============================================================================
# TESTS CYCLE DE VIE : SOUMISSION, VALIDATION & REJET (US-042)
# ==============================================================================


@pytest.mark.django_db
def test_workflow_soumettre_rapport(client_tenant, setup_chantier):
    """Passage d'un rapport de BROUILLON à SOUMIS."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]
    cl = authentifier(client_tenant, cc)

    rep_create = cl.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(projet.id),
            "lot_id": str(lot.id),
            "date_rapport": str(date.today()),
            "statut": StatutRapport.BROUILLON,
        },
        format="json",
    )
    rapport_id = rep_create.data["id"]

    rep_soumettre = cl.post(f"/api/v1/rapports/{rapport_id}/soumettre/")
    assert rep_soumettre.status_code == status.HTTP_200_OK
    assert rep_soumettre.data["statut"] == StatutRapport.SOUMIS
    assert rep_soumettre.data["soumis_le"] is not None


@pytest.mark.django_db
def test_workflow_rejet_ct_exige_motif_au_moins_20_caracteres(client_tenant, setup_chantier):
    """Le rejet par le CT exige un motif explicite d'au moins 20 caractères (chk_rejet_commente)."""
    cc = setup_chantier["cc"]
    ct = setup_chantier["ct"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]

    cl_cc = authentifier(client_tenant, cc)
    rep_create = cl_cc.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(projet.id),
            "lot_id": str(lot.id),
            "date_rapport": str(date.today()),
            "statut": StatutRapport.SOUMIS,
        },
        format="json",
    )
    rapport_id = rep_create.data["id"]

    cl_ct = APIClient(headers={"host": HOTE})
    cl_ct = authentifier(cl_ct, ct)

    # 1. Échec : motif trop court (ex: 10 caractères)
    rep_court = cl_ct.post(
        f"/api/v1/rapports/{rapport_id}/rejeter/",
        {"motif": "Non valide"},
        format="json",
    )
    assert rep_court.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )

    # 2. Succès : motif ≥ 20 caractères
    motif_valide = "Effectif régie incohérent avec le pointage de sécurité."
    assert len(motif_valide) >= 20
    rep_ok = cl_ct.post(
        f"/api/v1/rapports/{rapport_id}/rejeter/",
        {"motif": motif_valide},
        format="json",
    )
    assert rep_ok.status_code == status.HTTP_200_OK
    assert rep_ok.data["statut"] == StatutRapport.REJETE
    assert rep_ok.data["commentaire_validation"] == motif_valide


# ==============================================================================
# TESTS IMMUTABILITE : INTERDICTION DE SUPPRESSION (Socle Commun §3.1 / MLD §6.7)
# ==============================================================================


@pytest.mark.django_db
def test_interdiction_suppression_rapport(client_tenant, setup_chantier):
    """Un journal de chantier ne se supprime jamais : DELETE renvoie 405 et delete() bloque."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    cl = authentifier(client_tenant, cc)

    rep_create = cl.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(projet.id),
            "date_rapport": str(date.today()),
            "statut": StatutRapport.BROUILLON,
        },
        format="json",
    )
    rapport_id = rep_create.data["id"]

    # 1. Vérification au niveau API HTTP (405 Method Not Allowed)
    rep_del = cl.delete(f"/api/v1/rapports/{rapport_id}/")
    assert rep_del.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # 2. Vérification au niveau modèle Python (delete() lève une exception)
    with schema_context(SCHEMA):
        rapport = RapportJournalier.objects.get(id=rapport_id)
        with pytest.raises(ErreurMetier):
            rapport.delete()


# ==============================================================================
# TESTS LECTURE : LISTE PAGINEE & FILTRES (US-043)
# ==============================================================================


@pytest.mark.django_db
def test_lister_rapports_avec_filtres_et_pagination(client_tenant, setup_chantier):
    """Vérifie la pagination standard et le filtrage multi-critères sur les rapports."""
    cc = setup_chantier["cc"]
    projet = setup_chantier["projet"]
    lot = setup_chantier["lot"]
    cl = authentifier(client_tenant, cc)

    with schema_context(SCHEMA):
        # Créer 3 rapports à des dates différentes
        for i in range(3):
            RapportJournalier.objects.create(
                projet=projet,
                lot=lot,
                auteur=cc,
                date_rapport=date.today() - timedelta(days=i),
                meteo=Meteo.ENSOLEILLE if i == 0 else Meteo.PLUIE,
                statut=StatutRapport.SOUMIS if i < 2 else StatutRapport.BROUILLON,
                effectif_present=10,
            )

    # 1. Liste sans filtre
    rep_all = cl.get("/api/v1/rapports/")
    assert rep_all.status_code == status.HTTP_200_OK
    assert rep_all.data["total"] == 3
    assert len(rep_all.data["resultats"]) == 3

    # 2. Filtrer par statut SOUMIS
    rep_soumis = cl.get("/api/v1/rapports/?statut=SOUMIS")
    assert rep_soumis.status_code == status.HTTP_200_OK
    assert rep_soumis.data["total"] == 2

    # 3. Filtrer par météo PLUIE
    rep_pluie = cl.get("/api/v1/rapports/?meteo=PLUIE")
    assert rep_pluie.status_code == status.HTTP_200_OK
    assert rep_pluie.data["total"] == 2

    # 4. Consultation du détail d'un rapport
    premier_id = rep_all.data["resultats"][0]["id"]
    rep_detail = cl.get(f"/api/v1/rapports/{premier_id}/")
    assert rep_detail.status_code == status.HTTP_200_OK
    assert rep_detail.data["id"] == premier_id
    assert rep_detail.data["projet"]["id"] == str(projet.id)
