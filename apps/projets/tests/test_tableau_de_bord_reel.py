"""Tests d'intégration pour le Tableau de bord 100% réel (apps.projets)."""

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.chantier.models import RapportJournalier
from apps.core.enums import (
    RoleGlobal,
    RoleTiersChoix,
    StatutProjet,
    StatutRapport,
    StatutUtilisateur,
)
from apps.projets.models import Lot, Projet
from apps.tiers.models import RoleTiers, Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Password123!"


@pytest.mark.django_db
class TestTableauDeBordReel:
    @pytest.fixture
    def client(self):
        return APIClient(headers={"host": HOTE})

    @pytest.fixture
    def dg_user(self, db):
        with schema_context(SCHEMA):
            Utilisateur.tous_objets.filter(email="dg.dashreel@demo.ci").delete()
            dg = Utilisateur.objects.create_user(
                email="dg.dashreel@demo.ci",
                nom="Directeur",
                prenom="Général",
                password=MOT_DE_PASSE,
                role_global=RoleGlobal.DIRECTEUR_GENERAL,
                statut=StatutUtilisateur.ACTIF,
            )
            yield dg

    def test_tableau_de_bord_avec_donnees_reelles(self, client, dg_user):
        client.force_authenticate(user=dg_user)

        with schema_context(SCHEMA):
            # Nettoyage préalable dans l'ordre strict des dépendances
            RapportJournalier.objects.all().delete()
            Lot.objects.all().delete()
            Projet.objects.all().delete()
            RoleTiers.objects.all().delete()
            Tiers.objects.all().delete()

            client_moa = Tiers.objects.create(
                raison_sociale="Maître d'Ouvrage CI",
                telephone="0101010101",
            )
            RoleTiers.objects.create(tiers=client_moa, role=RoleTiersChoix.CLIENT_MOA)

            # 1. Projet
            p1 = Projet.objects.create(
                reference="PRJ-2026-001",
                nom="Tour Ivoire Tech",
                client=client_moa,
                chef_projet=dg_user,
                ville="Abidjan",
                date_debut_prevue="2026-01-01",
                date_fin_prevue="2026-12-31",
                budget_initial_montant=1_000_000_000,
                avancement_reel=25.0,
                avancement_theorique=20.0,
                statut=StatutProjet.EN_COURS,
            )

            # 2. Lot
            lot1 = Lot.objects.create(
                projet=p1,
                code="LOT-01",
                libelle="Fondations spéciales",
                ordre=1,
            )

            # 3. Rapport journalier avec effectifs réels
            today = timezone.localdate()
            RapportJournalier.objects.create(
                projet=p1,
                lot=lot1,
                auteur=dg_user,
                date_rapport=today,
                effectif_regie=12,
                effectif_tacherons=18,
                statut=StatutRapport.SOUMIS,
                observations="Coulage des pieux terminé",
            )

        # Appel GET dashboard (avec headers Host)
        response = client.get("/api/v1/tableau-de-bord/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data

        # Vérification des métriques agrégées
        assert data["aucun_chantier"] is False
        assert data["metriques"]["chantiers_actifs"] == 1
        assert data["metriques"]["chantiers_conformes"] == 1
        assert data["metriques"]["chantiers_en_retard"] == 0

        # Vérification effectifs réels
        assert data["metriques"]["effectifs_sur_site"]["regie"] == 12
        assert data["metriques"]["effectifs_sur_site"]["tacherons"] == 18
        assert data["metriques"]["effectifs_sur_site"]["total"] == 30

        # Vérification rapports réels
        assert data["metriques"]["rapports_journaliers"]["soumis"] == 1
        assert data["metriques"]["rapports_journaliers"]["attendus"] == 1

        # Vérification projet
        projet_res = data["projets"][0]
        assert projet_res["nom"] == "Tour Ivoire Tech"
        assert projet_res["rapport_jour_statut"] == "SOUMIS"

        # Nettoyage propre en fin de test
        with schema_context(SCHEMA):
            RapportJournalier.objects.all().delete()
            Lot.objects.all().delete()
            Projet.objects.all().delete()
            RoleTiers.objects.all().delete()
            Tiers.objects.all().delete()

    def test_tableau_de_bord_sante_globale_projets_actifs_et_badge(self, client, dg_user):
        client.force_authenticate(user=dg_user)

        with schema_context(SCHEMA):
            Projet.objects.all().delete()
            RoleTiers.objects.all().delete()
            Tiers.objects.all().delete()

            moa = Tiers.objects.create(raison_sociale="Client Dashboard", telephone="0202020202")
            RoleTiers.objects.create(tiers=moa, role=RoleTiersChoix.CLIENT_MOA)

            # Projet 1 actif : score 80, VERT
            Projet.objects.create(
                reference="PRJ-ACT-01",
                nom="Chantier Actif 1",
                client=moa,
                statut=StatutProjet.EN_COURS,
                indice_sante=80,
                badge_sante="VERT",
            )
            # Projet 2 actif : score 50, ORANGE
            Projet.objects.create(
                reference="PRJ-ACT-02",
                nom="Chantier Actif 2",
                client=moa,
                statut=StatutProjet.EN_RETARD,
                indice_sante=50,
                badge_sante="ORANGE",
            )
            # Projet 3 terminé (non actif) : score 95 -> doit être exclu de sante_globale
            Projet.objects.create(
                reference="PRJ-TERM-01",
                nom="Chantier Terminé",
                client=moa,
                statut=StatutProjet.TERMINE,
                indice_sante=95,
                badge_sante="VERT",
            )
            # Projet 4 actif sans activité / non calculé : indice_sante=None -> exclu de sante_globale
            Projet.objects.create(
                reference="PRJ-SANS-ACT",
                nom="Chantier Sans Activité",
                client=moa,
                statut=StatutProjet.EN_COURS,
                indice_sante=None,
                badge_sante=None,
            )

        response = client.get("/api/v1/tableau-de-bord/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data

        # sante_globale = moyenne des projets ACTIFS avec score non nul = (80 + 50) / 2 = 65
        assert data["metriques"]["sante_globale"] == 65

        projets_map = {p["reference"]: p for p in data["projets"]}
        assert projets_map["PRJ-ACT-01"]["indice_sante"] == 80
        assert projets_map["PRJ-ACT-01"]["badge_sante"] == "VERT"

        assert projets_map["PRJ-ACT-02"]["indice_sante"] == 50
        assert projets_map["PRJ-ACT-02"]["badge_sante"] == "ORANGE"

        assert projets_map["PRJ-TERM-01"]["indice_sante"] == 95
        assert projets_map["PRJ-TERM-01"]["badge_sante"] == "VERT"

        assert projets_map["PRJ-SANS-ACT"]["indice_sante"] is None
        assert projets_map["PRJ-SANS-ACT"]["badge_sante"] is None

        with schema_context(SCHEMA):
            Projet.objects.all().delete()
            RoleTiers.objects.all().delete()
            Tiers.objects.all().delete()

