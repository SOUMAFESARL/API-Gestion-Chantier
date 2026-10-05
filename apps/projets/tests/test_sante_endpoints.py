"""Tests d'intégration pour les endpoints de santé, arrêts de chantier et blocages.

Vérifie :
- Consultation synthétique, détaillée et historique de l'indice de santé
  (GET /api/v1/projets/{id}/sante/, /sante/detail/, /sante/historique/)
- Gestion complète des arrêts de chantier (GET, POST, PATCH, DELETE)
- Gestion complète des blocages et incidents de chantier (GET, POST, PATCH, prendre en charge, résoudre)
- Contrôles de permissions et d'affectation projet (403 / 404)
- Validations métier (incohérence de dates, etc.)
"""

import uuid
from datetime import date, timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.chantier.models import Blocage
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutBlocage,
    StatutProjet,
    StatutUtilisateur,
    TypeTiers,
)
from apps.projets.models import AffectationProjet, ArretChantier, Lot, Projet, SanteProjetSnapshot
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Pass12345!"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def setup_sante_data(db):
    """Prépare un jeu de données complet dans le schéma tenant."""
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        # Nettoyage préalable
        Blocage.objects.all().delete()
        ArretChantier.objects.all().delete()
        SanteProjetSnapshot.objects.all().delete()
        AffectationProjet.objects.all().delete()
        Lot.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(
            email__in=[
                "dg.testsante@demo.ci",
                "cp.testsante@demo.ci",
                "ct.testsante@demo.ci",
                "nonmembre.testsante@demo.ci",
            ]
        ).delete()

        # 1. Utilisateurs
        dg = Utilisateur.objects.create_user(
            email="dg.testsante@demo.ci",
            password=MOT_DE_PASSE,
            nom="Directeur",
            prenom="General",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
            is_owner=True,
        )

        cp = Utilisateur.objects.create_user(
            email="cp.testsante@demo.ci",
            password=MOT_DE_PASSE,
            nom="Kouame",
            prenom="ChefProjet",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )

        ct = Utilisateur.objects.create_user(
            email="ct.testsante@demo.ci",
            password=MOT_DE_PASSE,
            nom="Konan",
            prenom="Conducteur",
            role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
            statut=StatutUtilisateur.ACTIF,
        )

        non_membre = Utilisateur.objects.create_user(
            email="nonmembre.testsante@demo.ci",
            password=MOT_DE_PASSE,
            nom="Externe",
            prenom="Visiteur",
            role_global=RoleGlobal.VISITEUR,
            statut=StatutUtilisateur.ACTIF,
        )

        # 2. Client MOA
        client_tiers = Tiers.objects.create(
            type_tiers=TypeTiers.ENTREPRISE,
            raison_sociale="Société Immobilière Test",
            telephone="+2250102030405",
        )

        # 3. Projet EN_COURS
        today = date.today()
        projet_en_cours = Projet.objects.create(
            reference="PRJ-SANTE-001",
            nom="Tour Ivoire Santé",
            client=client_tiers,
            chef_projet=cp,
            conducteur_travaux=ct,
            date_debut_prevue=today - timedelta(days=60),
            date_fin_prevue=today + timedelta(days=120),
            budget_initial_montant=500_000_000,
            avancement_reel=45.0,
            avancement_theorique=50.0,
            indice_sante=85,
            badge_sante="VERT",
            indice_sante_calcule_le=timezone.now(),
            statut=StatutProjet.EN_COURS,
        )

        # 4. Projet EN_ATTENTE
        projet_en_attente = Projet.objects.create(
            reference="PRJ-SANTE-002",
            nom="Résidence En Attente",
            client=client_tiers,
            chef_projet=cp,
            date_debut_prevue=today + timedelta(days=15),
            date_fin_prevue=today + timedelta(days=180),
            budget_initial_montant=200_000_000,
            avancement_reel=0.0,
            avancement_theorique=0.0,
            indice_sante=None,
            badge_sante=None,
            statut=StatutProjet.EN_ATTENTE,
        )

        # 5. Lot
        lot1 = Lot.objects.create(
            projet=projet_en_cours,
            code="LOT-01",
            libelle="Gros Œuvre",
            ordre=1,
        )

        # 6. Affectations
        AffectationProjet.objects.create(
            projet=projet_en_cours,
            utilisateur=cp,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
        )
        AffectationProjet.objects.create(
            projet=projet_en_cours,
            utilisateur=ct,
            role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
            est_actif=True,
        )

        # 7. Snapshot historique
        snapshot = SanteProjetSnapshot.objects.create(
            projet=projet_en_cours,
            score=82,
            badge_brut="VERT",
            badge_final="VERT",
            p_delais=10.0,
            p_blocages=5.0,
            p_reporting=3.0,
            delta=5.0,
            avancement_physique=45.0,
            avancement_temporel=50.0,
            taux_reporting=85.0,
            date_calcul=timezone.now() - timedelta(days=1),
        )

        yield {
            "dg": dg,
            "cp": cp,
            "ct": ct,
            "non_membre": non_membre,
            "projet_en_cours": projet_en_cours,
            "projet_en_attente": projet_en_attente,
            "lot": lot1,
            "snapshot": snapshot,
        }

        # Nettoyage après tests
        Blocage.objects.all().delete()
        ArretChantier.objects.all().delete()
        SanteProjetSnapshot.objects.all().delete()
        AffectationProjet.objects.all().delete()
        Lot.objects.all().delete()
        Projet.objects.all().delete()
        Tiers.objects.all().delete()
        Utilisateur.tous_objets.filter(
            email__in=[
                "dg.testsante@demo.ci",
                "cp.testsante@demo.ci",
                "ct.testsante@demo.ci",
                "nonmembre.testsante@demo.ci",
            ]
        ).delete()


@pytest.mark.django_db
class TestSanteConsultationEndpoints:
    """Tests pour GET /sante/, /sante/detail/ et /sante/historique/."""

    def test_projet_sante_apercu_ok(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["cp"])
        p = setup_sante_data["projet_en_cours"]

        url = f"/api/v1/projets/{p.id}/sante/"
        response = client_tenant.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["projet_id"] == str(p.id)
        assert data["reference"] == p.reference
        assert data["indice_sante"] == 85
        assert data["badge_sante"] == "VERT"
        assert data["avancement_reel"] == 45.0
        assert data["avancement_theorique"] == 50.0
        assert data["ecart"] == -5.0

    def test_projet_sante_apercu_projet_en_attente(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["dg"])
        p = setup_sante_data["projet_en_attente"]

        url = f"/api/v1/projets/{p.id}/sante/"
        response = client_tenant.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["indice_sante"] == 100
        assert data["badge_sante"] == "VERT"

    def test_projet_sante_detail_ok(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["cp"])
        p = setup_sante_data["projet_en_cours"]

        url = f"/api/v1/projets/{p.id}/sante/detail/"
        response = client_tenant.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["projet_id"] == str(p.id)
        assert data["etat_calcul"] == "ACTIF"
        assert "score" in data
        assert "badge" in data
        assert "penalite_delais" in data
        assert "penalite_blocages" in data
        assert "penalite_reporting" in data
        assert "retard_pts" in data
        assert "avancement_physique" in data
        assert "blocages_critiques" in data
        assert "blocages_majeurs" in data
        assert "blocages_moderes" in data
        assert "taux_reporting" in data
        assert "avertissements" in data

    def test_projet_sante_historique_ok(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["cp"])
        p = setup_sante_data["projet_en_cours"]

        url = f"/api/v1/projets/{p.id}/sante/historique/"
        response = client_tenant.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["score"] == 82
        assert data[0]["badge"] == "VERT"

    def test_projet_sante_non_trouve_404(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["dg"])
        faux_id = uuid.uuid4()

        assert client_tenant.get(f"/api/v1/projets/{faux_id}/sante/").status_code == status.HTTP_404_NOT_FOUND
        assert client_tenant.get(f"/api/v1/projets/{faux_id}/sante/detail/").status_code == status.HTTP_404_NOT_FOUND
        assert client_tenant.get(f"/api/v1/projets/{faux_id}/sante/historique/").status_code == status.HTTP_404_NOT_FOUND

    def test_projet_sante_acces_refuse_non_membre(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["non_membre"])
        p = setup_sante_data["projet_en_cours"]

        url = f"/api/v1/projets/{p.id}/sante/"
        response = client_tenant.get(url)
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


@pytest.mark.django_db
class TestArretChantierEndpoints:
    """Tests pour les arrêts de chantier."""

    def test_arret_chantier_crud_workflow(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["dg"])
        p = setup_sante_data["projet_en_cours"]

        # 1. Créer un arrêt
        payload_creation = {
            "date_debut": "2026-05-01",
            "date_fin": "2026-05-10",
            "motif": "Arrêt préfectoral temporaire",
        }
        res_post = client_tenant.post(
            f"/api/v1/projets/{p.id}/arrets-chantier/",
            data=payload_creation,
            format="json",
        )
        assert res_post.status_code == status.HTTP_201_CREATED
        arret_data = res_post.json()
        arret_id = arret_data["id"]
        assert arret_data["motif"] == "Arrêt préfectoral temporaire"
        assert arret_data["date_debut"] == "2026-05-01"
        assert arret_data["date_fin"] == "2026-05-10"
        assert arret_data["est_en_cours"] is False

        # 2. Lister les arrêts
        res_list = client_tenant.get(f"/api/v1/projets/{p.id}/arrets-chantier/")
        assert res_list.status_code == status.HTTP_200_OK
        assert len(res_list.json()) == 1

        # 3. Modifier l'arrêt (PATCH)
        res_patch = client_tenant.patch(
            f"/api/v1/arrets-chantier/{arret_id}/",
            data={"motif": "Arrêt préfectoral prolongé"},
            format="json",
        )
        assert res_patch.status_code == status.HTTP_200_OK
        assert res_patch.json()["motif"] == "Arrêt préfectoral prolongé"

        # 4. Supprimer l'arrêt (DELETE)
        res_delete = client_tenant.delete(f"/api/v1/arrets-chantier/{arret_id}/")
        assert res_delete.status_code == status.HTTP_204_NO_CONTENT

        # Vérifier qu'il n'apparaît plus dans la liste
        res_list2 = client_tenant.get(f"/api/v1/projets/{p.id}/arrets-chantier/")
        assert len(res_list2.json()) == 0

    def test_arret_chantier_dates_invalides(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["dg"])
        p = setup_sante_data["projet_en_cours"]

        payload = {
            "date_debut": "2026-05-15",
            "date_fin": "2026-05-10",  # date_fin < date_debut
            "motif": "Erreur de dates",
        }
        response = client_tenant.post(
            f"/api/v1/projets/{p.id}/arrets-chantier/",
            data=payload,
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_arret_chantier_permission_refusee(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["non_membre"])
        p = setup_sante_data["projet_en_cours"]

        payload = {
            "date_debut": "2026-05-01",
            "motif": "Tentative non autorisée",
        }
        response = client_tenant.post(
            f"/api/v1/projets/{p.id}/arrets-chantier/",
            data=payload,
            format="json",
        )
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


@pytest.mark.django_db
class TestBlocageEndpoints:
    """Tests pour les blocages de chantier."""

    def test_blocage_crud_et_workflow(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["dg"])
        p = setup_sante_data["projet_en_cours"]
        lot = setup_sante_data["lot"]

        # 1. Déclarer un blocage (POST)
        payload = {
            "titre": "Rupture de stock ciment CPJ 42.5",
            "severite": "MAJEUR",
            "description": "Fournisseur local en rupture d'approvisionnement",
            "date_signalement": str(date.today()),
            "lot_id": str(lot.id),
        }
        res_post = client_tenant.post(
            f"/api/v1/projets/{p.id}/blocages/",
            data=payload,
            format="json",
        )
        assert res_post.status_code == status.HTTP_201_CREATED
        data_blocage = res_post.json()
        blocage_id = data_blocage["id"]
        assert data_blocage["titre"] == payload["titre"]
        assert data_blocage["severite"] == "MAJEUR"
        assert data_blocage["statut"] == StatutBlocage.OUVERT

        # 2. Lister les blocages du projet
        res_list = client_tenant.get(f"/api/v1/projets/{p.id}/blocages/")
        assert res_list.status_code == status.HTTP_200_OK
        assert len(res_list.json()) == 1

        # 3. Consulter le détail du blocage
        res_detail = client_tenant.get(f"/api/v1/blocages/{blocage_id}/")
        assert res_detail.status_code == status.HTTP_200_OK
        assert res_detail.json()["id"] == blocage_id

        # 4. Modifier le blocage (PATCH)
        res_patch = client_tenant.patch(
            f"/api/v1/blocages/{blocage_id}/",
            data={"severite": "CRITIQUE", "description": "Rupture nationale"},
            format="json",
        )
        assert res_patch.status_code == status.HTTP_200_OK
        assert res_patch.json()["severite"] == "CRITIQUE"

        # 5. Prendre en charge
        res_pec = client_tenant.post(f"/api/v1/blocages/{blocage_id}/prendre-en-charge/")
        assert res_pec.status_code == status.HTTP_200_OK
        assert res_pec.json()["statut"] == StatutBlocage.PRIS_EN_CHARGE

        # 6. Résoudre
        res_res = client_tenant.post(
            f"/api/v1/blocages/{blocage_id}/resoudre/",
            data={"commentaire": "Livraison reçue depuis San Pedro"},
            format="json",
        )
        assert res_res.status_code == status.HTTP_200_OK
        assert res_res.json()["statut"] == StatutBlocage.RESOLU
        assert res_res.json()["resolu_le"] is not None

    def test_blocage_permission_refusee(self, client_tenant, setup_sante_data):
        client_tenant.force_authenticate(user=setup_sante_data["non_membre"])
        p = setup_sante_data["projet_en_cours"]

        payload = {
            "titre": "Blocage non autorisé",
            "severite": "MINEUR",
        }
        response = client_tenant.post(
            f"/api/v1/projets/{p.id}/blocages/",
            data=payload,
            format="json",
        )
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
