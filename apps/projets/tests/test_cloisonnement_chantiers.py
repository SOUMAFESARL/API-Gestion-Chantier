"""Tests d'intégration pour le cloisonnement hermétique des chantiers (Sprint 3 - Tâche 07).

Vérifie l'étanchéité stricte :
1. DG et Administrateur : vision consolidée universelle de tous les chantiers.
2. Les collaborateurs voient uniquement leurs chantiers affectes.
3. Tentative d'accès direct GET/PATCH/DELETE /projets/{id}/ sur un chantier tiers : 403 Forbidden.
4. Tentative de lecture ou gestion d'équipe /affectations/ sur un chantier tiers : 403 Forbidden.
5. Tentative de création de rapport journalier sur un chantier non affecté : 400 Bad Request.
6. Scoping automatique du tableau de bord décisionnel (/tableau-de-bord/).
"""

from datetime import date

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import (
    Meteo,
    RoleGlobal,
    RoleProjet,
    StatutProjet,
    StatutUtilisateur,
    TypeTiers,
)
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "PassCloisonne123!"

pytestmark = pytest.mark.django_db


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def fixtures_cloisonnement(db):
    """Initialise un écosystème à deux chantiers étanches et différents profils."""
    with schema_context(SCHEMA):
        # 0. Initialisation des rôles, modules et habilitations par défaut
        initialiser_roles_par_defaut()

        # 1. Client maître d'ouvrage
        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="BTP Immobilier Invest",
            defaults={"type_tiers": TypeTiers.ENTREPRISE, "ville": "Abidjan"},
        )

        # 2. Utilisateurs
        def creer_user(email, nom, prenom, role, is_owner=False):
            u, _ = Utilisateur.tous_objets.get_or_create(
                email=email,
                defaults={
                    "nom": nom,
                    "prenom": prenom,
                    "role_global": role,
                    "statut": StatutUtilisateur.ACTIF,
                    "is_owner": is_owner,
                },
            )
            u.role_global = role
            u.is_owner = is_owner
            u.password = make_password(MOT_DE_PASSE)
            u.save()
            return u

        dg = creer_user(
            "dg.clois@demo.ci", "Directeur", "General", RoleGlobal.DIRECTEUR_GENERAL, is_owner=True
        )
        admin = creer_user(
            "admin.clois@demo.ci", "Admin", "Delegue", RoleGlobal.ADMIN, is_owner=False
        )
        cp_a = creer_user("cp.a.clois@demo.ci", "Kouassi", "ChefA", RoleGlobal.CHEF_PROJET)
        cp_b = creer_user("cp.b.clois@demo.ci", "Toure", "ChefB", RoleGlobal.CHEF_PROJET)
        ct_a = creer_user(
            "ct.a.clois@demo.ci", "Diallo", "ConducteurA", RoleGlobal.CONDUCTEUR_TRAVAUX
        )
        cc_b = creer_user("cc.b.clois@demo.ci", "Kone", "ChefChantierB", RoleGlobal.CHEF_CHANTIER)

        # 3. Chantier A (Attribué à CP A et CT A)
        projet_a = Projet.objects.create(
            reference="PRJ-A-ADJAME",
            nom="Résidence Adjamé Nord",
            client=client_tiers,
            ville="Adjamé",
            chef_projet=cp_a,
            conducteur_travaux=ct_a,
            date_debut_prevue=date(2026, 10, 1),
            date_fin_prevue=date(2027, 3, 31),
            budget_initial_montant=50000000,
            statut=StatutProjet.EN_COURS,
        )
        AffectationProjet.objects.create(
            projet=projet_a,
            utilisateur=cp_a,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        )
        AffectationProjet.objects.create(
            projet=projet_a,
            utilisateur=ct_a,
            role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
            est_actif=True,
        )
        lot_a = Lot.objects.create(projet=projet_a, code="L-01", libelle="Gros Œuvre Adjamé")

        # 4. Chantier B (Attribué à CP B et CC B)
        projet_b = Projet.objects.create(
            reference="PRJ-B-COCODY",
            nom="Tour Résidentielle Cocody",
            client=client_tiers,
            ville="Cocody",
            chef_projet=cp_b,
            date_debut_prevue=date(2026, 11, 1),
            date_fin_prevue=date(2027, 8, 31),
            budget_initial_montant=120000000,
            statut=StatutProjet.EN_COURS,
        )
        AffectationProjet.objects.create(
            projet=projet_b,
            utilisateur=cp_b,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        )
        AffectationProjet.objects.create(
            projet=projet_b,
            utilisateur=cc_b,
            role_projet=RoleProjet.CHEF_CHANTIER,
            est_actif=True,
        )
        lot_b = Lot.objects.create(projet=projet_b, code="L-01", libelle="Terrassement Cocody")

        return {
            "dg": dg,
            "admin": admin,
            "cp_a": cp_a,
            "cp_b": cp_b,
            "ct_a": ct_a,
            "cc_b": cc_b,
            "projet_a": projet_a,
            "projet_b": projet_b,
            "lot_a": lot_a,
            "lot_b": lot_b,
        }


def test_dg_et_admin_voient_tous_les_chantiers(fixtures_cloisonnement):
    """Le DG et l'administrateur disposent d'une vue consolidée de tous les chantiers."""
    f = fixtures_cloisonnement
    client = APIClient()

    for user in (f["dg"], f["admin"]):
        _auth(client, user)
        rep = client.get("/api/v1/projets/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()
        ids = [p["reference"] for p in data]
        assert f["projet_a"].reference in ids
        assert f["projet_b"].reference in ids


def test_collaborateur_ne_voit_que_ses_chantiers(fixtures_cloisonnement):
    """Un collaborateur opérationnel ne voit que les chantiers auxquels il est affecté."""
    f = fixtures_cloisonnement
    client = APIClient()

    # CP A voit uniquement Chantier A
    _auth(client, f["cp_a"])
    rep_a = client.get("/api/v1/projets/", HTTP_HOST=HOTE)
    assert rep_a.status_code == status.HTTP_200_OK
    ids_a = [p["reference"] for p in rep_a.json()]
    assert f["projet_a"].reference in ids_a
    assert f["projet_b"].reference not in ids_a

    # CP B voit uniquement Chantier B
    _auth(client, f["cp_b"])
    rep_b = client.get("/api/v1/projets/", HTTP_HOST=HOTE)
    assert rep_b.status_code == status.HTTP_200_OK
    ids_b = [p["reference"] for p in rep_b.json()]
    assert f["projet_b"].reference in ids_b
    assert f["projet_a"].reference not in ids_b


def test_acces_direct_projet_tiers_interdit(fixtures_cloisonnement):
    """Tentative d'accès par URL directe (GET, PATCH, DELETE) sur un chantier tiers renvoie 403."""
    f = fixtures_cloisonnement
    client = APIClient()

    _auth(client, f["cp_a"])
    url_b = f"/api/v1/projets/{f['projet_b'].id}/"

    # GET
    assert client.get(url_b, HTTP_HOST=HOTE).status_code == status.HTTP_403_FORBIDDEN

    # PATCH
    assert (
        client.patch(
            url_b, {"nom": "Tentative Piratage"}, format="json", HTTP_HOST=HOTE
        ).status_code
        == status.HTTP_403_FORBIDDEN
    )

    # DELETE
    assert client.delete(url_b, HTTP_HOST=HOTE).status_code == status.HTTP_403_FORBIDDEN


def test_affectations_equipe_chantier_tiers_interdite(fixtures_cloisonnement):
    """Les collaborateurs ne voient pas les equipes et projets tiers."""
    f = fixtures_cloisonnement
    client = APIClient()

    # 1. CT A tente de lister l'équipe du Chantier B
    _auth(client, f["ct_a"])
    url_aff_b = f"/api/v1/projets/{f['projet_b'].id}/affectations/"
    rep_get = client.get(url_aff_b, HTTP_HOST=HOTE)
    assert rep_get.status_code == status.HTTP_403_FORBIDDEN

    # 2. CP A tente d'affecter un membre sur le Chantier B (même s'il a le rôle CP global)
    _auth(client, f["cp_a"])
    rep_post = client.post(
        url_aff_b,
        {
            "utilisateur_id": str(f["ct_a"].id),
            "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_post.status_code == status.HTTP_403_FORBIDDEN

    # 3. En revanche, le CP B assigné ou le DG peut affecter un membre sur le Chantier B
    _auth(client, f["cp_b"])
    rep_post_ok = client.post(
        url_aff_b,
        {
            "utilisateur_id": str(f["ct_a"].id),
            "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_post_ok.status_code == status.HTTP_201_CREATED


def test_creation_rapport_hors_chantier_affecte_interdite(fixtures_cloisonnement):
    """La création d'un rapport journalier sur un projet non affecté est refusée (400)."""
    f = fixtures_cloisonnement
    client = APIClient()

    # CT A tente de créer un rapport sur Chantier B
    _auth(client, f["ct_a"])
    rep_refus = client.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(f["projet_b"].id),
            "lot_id": str(f["lot_b"].id),
            "date_rapport": str(timezone.now().date()),
            "meteo": Meteo.ENSOLEILLE,
            "effectif_regie": 5,
            "effectif_tacherons": 10,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_refus.status_code == status.HTTP_400_BAD_REQUEST
    data_refus = rep_refus.json()
    details = data_refus.get("erreur", {}).get("details", data_refus)
    assert "projet_id" in details

    # CT A crée un rapport sur son propre Chantier A
    rep_ok = client.post(
        "/api/v1/rapports/",
        {
            "projet_id": str(f["projet_a"].id),
            "lot_id": str(f["lot_a"].id),
            "date_rapport": str(timezone.now().date()),
            "meteo": Meteo.ENSOLEILLE,
            "effectif_regie": 5,
            "effectif_tacherons": 10,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_ok.status_code == status.HTTP_201_CREATED


def test_tableau_de_bord_scoping_par_affectation(fixtures_cloisonnement):
    """Le tableau de bord décisionnel n'agrège que les données des chantiers affectés."""
    f = fixtures_cloisonnement
    client = APIClient()

    # CP A consulte le tableau de bord : uniquement Chantier A
    _auth(client, f["cp_a"])
    rep_a = client.get("/api/v1/tableau-de-bord/", HTTP_HOST=HOTE)
    assert rep_a.status_code == status.HTTP_200_OK
    projets_data_a = rep_a.json()["projets"]
    assert len(projets_data_a) == 1
    assert projets_data_a[0]["id"] == str(f["projet_a"].id)

    # DG consulte le tableau de bord : consolidation globale des deux chantiers
    _auth(client, f["dg"])
    rep_dg = client.get("/api/v1/tableau-de-bord/", HTTP_HOST=HOTE)
    assert rep_dg.status_code == status.HTTP_200_OK
    projets_data_dg = rep_dg.json()["projets"]
    assert len(projets_data_dg) == 2


def test_annuaire_collaborateurs_projets_cloisonnes(fixtures_cloisonnement):
    """Les collaborateurs ne voient pas les equipes et projets tiers."""
    f = fixtures_cloisonnement
    client = APIClient()

    # CT A consulte l'annuaire des collaborateurs
    _auth(client, f["ct_a"])
    rep = client.get("/api/v1/parametres/collaborateurs/", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()

    # Trouver l'entrée de CC B (qui n'est que sur le Chantier B)
    cc_b_entry = next((u for u in data if u["id"] == str(f["cc_b"].id)), None)
    assert cc_b_entry is not None
    # Pour CT A, les projets de CC B ne doivent pas afficher le Chantier B
    assert cc_b_entry["projets"] == []

    # En revanche, pour le DG, les projets de CC B affichent bien Chantier B
    _auth(client, f["dg"])
    rep_dg = client.get("/api/v1/parametres/collaborateurs/", HTTP_HOST=HOTE)
    assert rep_dg.status_code == status.HTTP_200_OK
    cc_b_dg_entry = next((u for u in rep_dg.json() if u["id"] == str(f["cc_b"].id)), None)
    assert cc_b_dg_entry is not None
    assert len(cc_b_dg_entry["projets"]) >= 1
    assert cc_b_dg_entry["projets"][0]["id"] == str(f["projet_b"].id)
