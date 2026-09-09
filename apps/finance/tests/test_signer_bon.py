"""Tests d'intégration pour la signature des bons de paiement (apps.finance)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleTiersChoix, StatutBonPaiement, StatutUtilisateur
from apps.finance.models import BonPaiement, SignatureBon
from apps.projets.models import Projet
from apps.tiers.models import RoleTiers, Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"
MOT_DE_PASSE = "Password123!"


@pytest.mark.django_db
class TestSignatureBonPaiement:
    @pytest.fixture
    def client(self):
        return APIClient(headers={"host": HOTE})

    @pytest.fixture
    def dg_user(self, db):
        with schema_context(SCHEMA):
            Utilisateur.tous_objets.filter(email="dg.signtest@demo.ci").delete()
            dg = Utilisateur.objects.create_user(
                email="dg.signtest@demo.ci",
                nom="Directeur",
                prenom="Général",
                password=MOT_DE_PASSE,
                role_global=RoleGlobal.DIRECTEUR_GENERAL,
                statut=StatutUtilisateur.ACTIF,
            )
            yield dg

    @pytest.fixture
    def visiteur_user(self, db):
        with schema_context(SCHEMA):
            Utilisateur.tous_objets.filter(email="visiteur.signtest@demo.ci").delete()
            visiteur = Utilisateur.objects.create_user(
                email="visiteur.signtest@demo.ci",
                nom="Visiteur",
                prenom="Simple",
                password=MOT_DE_PASSE,
                role_global=RoleGlobal.VISITEUR,
                statut=StatutUtilisateur.ACTIF,
            )
            yield visiteur

    @pytest.fixture
    def bon_a_signer(self, db, dg_user):
        with schema_context(SCHEMA):
            client_tier = Tiers.objects.create(
                raison_sociale="Client BTP Test Sign",
                telephone="0102030405",
            )
            RoleTiers.objects.create(tiers=client_tier, role=RoleTiersChoix.CLIENT_MOA)

            projet = Projet.objects.create(
                reference="PRJ-SIGN-001",
                nom="Chantier Test Sign",
                client=client_tier,
                chef_projet=dg_user,
                ville="Abidjan",
                date_debut_prevue="2026-01-01",
                date_fin_prevue="2026-12-31",
                budget_initial_montant=500_000_000,
            )

            tacheron = Tiers.objects.create(
                raison_sociale="Entreprise Sanogo Test",
                telephone="0708091011",
            )
            RoleTiers.objects.create(tiers=tacheron, role=RoleTiersChoix.TACHERON)

            bon = BonPaiement.objects.create(
                numero="BDP-TEST-001",
                projet=projet,
                beneficiaire=tacheron,
                corps_etat="Ferraillage et Coulage Voiles",
                montant_brut=2_500_000_00,  # 2 500 000 FCFA
                montant_net=2_500_000_00,
                statut=StatutBonPaiement.A_SIGNER,
            )
            yield bon

    def test_signature_par_dg_succes(self, client, dg_user, bon_a_signer):
        client.force_authenticate(user=dg_user)
        url = f"/api/v1/finance/bons-paiement/{bon_a_signer.id}/signer/"
        response = client.post(url, {"commentaire": "Travaux vérifiés sur site"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["succes"] is True
        assert response.data["statut"] == StatutBonPaiement.SIGNE

        with schema_context(SCHEMA):
            bon_a_signer.refresh_from_db()
            assert bon_a_signer.statut == StatutBonPaiement.SIGNE

            sig = SignatureBon.objects.filter(bon_paiement=bon_a_signer).first()
            assert sig is not None
            assert sig.signataire == dg_user
            assert sig.commentaire == "Travaux vérifiés sur site"

    def test_signature_par_role_non_autorise_refusee(self, client, visiteur_user, bon_a_signer):
        client.force_authenticate(user=visiteur_user)
        url = f"/api/v1/finance/bons-paiement/{bon_a_signer.id}/signer/"
        response = client.post(url, {})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "permission_refusee"

        with schema_context(SCHEMA):
            bon_a_signer.refresh_from_db()
            assert bon_a_signer.statut == StatutBonPaiement.A_SIGNER
