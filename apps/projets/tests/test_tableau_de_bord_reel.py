"""Tests d'intégration pour le Tableau de bord 100% réel (apps.projets)."""

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.achats.models import ReceptionMateriau
from apps.chantier.models import RapportJournalier
from apps.core.enums import (
    RoleGlobal,
    RoleTiersChoix,
    StatutBonPaiement,
    StatutProjet,
    StatutRapport,
    StatutUtilisateur,
)
from apps.finance.models import BonPaiement
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
            BonPaiement.objects.all().delete()
            ReceptionMateriau.objects.all().delete()
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

            tacheron = Tiers.objects.create(
                raison_sociale="Tâcheron Gros Œuvre",
                telephone="0202020202",
            )
            RoleTiers.objects.create(tiers=tacheron, role=RoleTiersChoix.TACHERON)

            fournisseur = Tiers.objects.create(
                raison_sociale="Ciments d'Abidjan",
                telephone="0303030303",
            )
            RoleTiers.objects.create(tiers=fournisseur, role=RoleTiersChoix.FOURNISSEUR)

            # 1. Projet
            p1 = Projet.objects.create(
                reference="PRJ-2026-001",
                nom="Tour Ivoire Tech",
                client=client_moa,
                chef_projet=dg_user,
                ville="Abidjan",
                date_debut_prevue="2026-01-01",
                date_fin_prevue="2026-12-31",
                budget_initial_montant=1_000_000_000,  # 10 000 000 FCFA
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

            # 4. Bons de paiement réels (1 A_SIGNER, 1 SIGNE)
            BonPaiement.objects.create(
                numero="BDP-2026-001",
                projet=p1,
                lot=lot1,
                beneficiaire=tacheron,
                corps_etat="Pieux",
                montant_brut=1_500_000_00,
                montant_net=1_500_000_00,
                statut=StatutBonPaiement.A_SIGNER,
            )
            BonPaiement.objects.create(
                numero="BDP-2026-002",
                projet=p1,
                lot=lot1,
                beneficiaire=tacheron,
                corps_etat="Terrassement",
                montant_brut=2_000_000_00,
                montant_net=2_000_000_00,
                statut=StatutBonPaiement.SIGNE,
            )

            # 5. Réception de matériaux réelle
            ReceptionMateriau.objects.create(
                projet=p1,
                fournisseur=fournisseur,
                designation="500 sacs de ciment CPJ 42.5",
                quantite=500,
                conforme=True,
                date_reception=today,
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

        # Vérification bons à signer
        assert data["metriques"]["bons_a_signer_count"] == 1
        assert data["metriques"]["bons_a_signer_montant"] == 1_500_000_00
        assert len(data["bons_paiement_a_valider"]) == 1
        assert data["bons_paiement_a_valider"][0]["reference"] == "BDP-2026-001"

        # Vérification réceptions
        assert len(data["receptions_materiaux"]) == 1
        assert data["receptions_materiaux"][0]["description"] == "500 sacs de ciment CPJ 42.5"
        assert data["receptions_materiaux"][0]["conforme"] is True

        # Vérification projet
        projet_res = data["projets"][0]
        assert projet_res["nom"] == "Tour Ivoire Tech"
        assert projet_res["rapport_jour_statut"] == "SOUMIS"
        assert projet_res["budget_consomme_montant"] == 2_000_000_00  # Bon signé

        # Nettoyage propre en fin de test
        with schema_context(SCHEMA):
            BonPaiement.objects.all().delete()
            ReceptionMateriau.objects.all().delete()
            RapportJournalier.objects.all().delete()
            Lot.objects.all().delete()
            Projet.objects.all().delete()
            RoleTiers.objects.all().delete()
            Tiers.objects.all().delete()
