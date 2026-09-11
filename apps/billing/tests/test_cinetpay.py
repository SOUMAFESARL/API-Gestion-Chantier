"""Tests d'intégration pour le paiement CinetPay (Guichet Hébergé) et facturation OHADA."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Facture, PaiementAbonnement, Plan
from apps.billing.services.paiement import PaiementAbonnementService
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.tenants.models import Entreprise

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def entreprise_et_admin(db):
    """Prépare les plans BTP, une entreprise de test et un administrateur."""
    call_command("peupler_plans", verbosity=0)

    with schema_context(get_public_schema_name()):
        entreprise = Entreprise.objects.get(schema_name=SCHEMA)
        entreprise.statut = StatutEntreprise.ESSAI
        entreprise.email_contact = "contact@entreprise-btp.ci"
        entreprise.save()

        plan_mo = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)
        aujourdhui = timezone.localdate()

        Abonnement.objects.filter(entreprise=entreprise).delete()
        abonnement = Abonnement.objects.create(
            entreprise=entreprise,
            plan=plan_mo,
            date_debut=aujourdhui,
            date_fin=aujourdhui + timedelta(days=14),
            fin_essai=aujourdhui + timedelta(days=14),
            statut=Abonnement.Statut.ESSAI,
        )

    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.cinetpay@demo.ci").delete()
        admin = Utilisateur.objects.create_user(
            email="admin.cinetpay@demo.ci",
            password="MotDePasse1!",
            nom="Konan",
            prenom="Aya",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )

    return {"entreprise": entreprise, "abonnement": abonnement, "admin": admin}


@pytest.mark.django_db
def test_catalogue_plans_btp(client_tenant, entreprise_et_admin):
    """L'endpoint public /api/v1/plans/ renvoie les 3 forfaits BTP avec leurs tarifs."""
    url = "/api/v1/plans/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 3

    codes = [p["code"] for p in data]
    assert Plan.Code.BATISSEUR in codes
    assert Plan.Code.MAITRE_OEUVRE in codes
    assert Plan.Code.PROMOTEUR in codes

    # Vérification des tarifs calculés en FCFA
    mo = next(p for p in data if p["code"] == Plan.Code.MAITRE_OEUVRE)
    assert mo["libelle"] == "Maître d'Œuvre"
    assert mo["prix_mensuel_fcfa"] == 49000
    assert mo["prix_annuel_fcfa"] == 490000


@pytest.mark.django_db
def test_initier_paiement_cinetpay(client_tenant, entreprise_et_admin):
    """Un client connecté peut initier un paiement CinetPay pour son abonnement."""
    admin = entreprise_et_admin["admin"]
    client_tenant.force_authenticate(user=admin)

    url = "/api/v1/cinetpay/initier/"
    payload = {
        "plan_code": Plan.Code.MAITRE_OEUVRE,
        "cycle": "MENSUEL",
    }
    response = client_tenant.post(url, payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "payment_url" in data
    assert "transaction_id" in data
    assert data["forfait"] == "Maître d'Œuvre"
    assert data["montant_fcfa"] == 49000

    # Vérification en base de données
    with schema_context(get_public_schema_name()):
        tx_id = data["transaction_id"]
        paiement = PaiementAbonnement.objects.get(reference_transaction=tx_id)
        assert paiement.statut == PaiementAbonnement.Statut.INITIE
        assert paiement.montant_fcfa == 49000

        facture = paiement.facture
        assert facture.statut == Facture.Statut.EMISE
        assert facture.numero.startswith(f"FAC-{timezone.localdate().year}-")
        assert facture.montant_ttc_fcfa == 49000


@pytest.mark.django_db
def test_webhook_cinetpay_validation_et_synchronisation(entreprise_et_admin):
    """Le webhook valide le paiement, la facture, et active abonnement + entreprise."""
    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    # 1. Initiation
    res = PaiementAbonnementService.initier_paiement(
        entreprise=entreprise,
        plan=plan,
        cycle="MENSUEL",
    )
    tx_id = res["transaction_id"]

    # 2. Simulation de notification webhook IPN
    donnees_ipn = {
        "cpm_trans_id": tx_id,
        "cpm_site_id": "TEST_SITE",
        "cpm_amount": "49000",
        "cpm_currency": "XOF",
        "payment_method": "WAVE",
    }

    resultat = PaiementAbonnementService.traiter_notification_webhook(
        transaction_id=tx_id,
        donnees_webhook=donnees_ipn,
    )

    assert resultat["statut"] == "CONFIRME"
    assert "facture" in resultat

    with schema_context(get_public_schema_name()):
        # Vérification du paiement
        paiement = PaiementAbonnement.objects.get(reference_transaction=tx_id)
        assert paiement.statut == PaiementAbonnement.Statut.CONFIRME
        assert paiement.mode == PaiementAbonnement.Mode.WAVE
        assert paiement.paye_le is not None

        # Vérification de la facture
        facture = paiement.facture
        assert facture.statut == Facture.Statut.PAYEE

        # Vérification de l'abonnement
        abonnement = facture.abonnement
        assert abonnement.statut == Abonnement.Statut.ACTIF
        assert abonnement.date_fin > timezone.localdate()

        # Vérification de la règle R-113 (Abonnement et Entreprise bougent ensemble)
        entreprise.refresh_from_db()
        assert entreprise.statut == StatutEntreprise.ACTIF


@pytest.mark.django_db
def test_webhook_cinetpay_idempotence(entreprise_et_admin):
    """Le traitement répété d'un webhook ne provoque aucun double débit ou extension."""
    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    res = PaiementAbonnementService.initier_paiement(
        entreprise=entreprise,
        plan=plan,
        cycle="MENSUEL",
    )
    tx_id = res["transaction_id"]

    # Premier passage
    res1 = PaiementAbonnementService.traiter_notification_webhook(tx_id)
    assert res1["statut"] == "CONFIRME"

    with schema_context(get_public_schema_name()):
        date_fin_initiale = Abonnement.objects.get(entreprise=entreprise).date_fin

    # Deuxième passage identique (Rejeu CinetPay)
    res2 = PaiementAbonnementService.traiter_notification_webhook(tx_id)
    assert res2["statut"] == "DEJA_CONFIRME"

    with schema_context(get_public_schema_name()):
        date_fin_apres = Abonnement.objects.get(entreprise=entreprise).date_fin
        # La date d'expiration ne doit PAS avoir augmenté une seconde fois
        assert date_fin_initiale == date_fin_apres
        # Le nombre de paiements reste exactement 1
        assert PaiementAbonnement.objects.filter(reference_transaction=tx_id).count() == 1


@pytest.mark.django_db
def test_consulter_statut_paiement_api(client_tenant, entreprise_et_admin):
    """L'endpoint statut permet au frontend de vérifier l'état du paiement."""
    admin = entreprise_et_admin["admin"]
    client_tenant.force_authenticate(user=admin)
    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    res = PaiementAbonnementService.initier_paiement(
        entreprise=entreprise,
        plan=plan,
        cycle="MENSUEL",
    )
    tx_id = res["transaction_id"]

    url = f"/api/v1/cinetpay/statut/{tx_id}/"
    response = client_tenant.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["transaction_id"] == tx_id
    assert data["statut"] in ["CONFIRME", "INITIE"]
    assert data["montant_fcfa"] == 49000
    assert data["reference_facture"] is not None
    assert data["entreprise"] == entreprise.raison_sociale


@pytest.mark.django_db
def test_webhook_cinetpay_hmac_valide_et_invalide(client_tenant, entreprise_et_admin, settings):
    """Le webhook valide les requêtes avec signature HMAC correcte et rejette les fausses."""
    import hashlib
    import hmac
    import json

    settings.CINETPAY_SECRET_KEY = "cle_secrete_ultra_securisee"
    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    res = PaiementAbonnementService.initier_paiement(
        entreprise=entreprise,
        plan=plan,
        cycle="MENSUEL",
    )
    tx_id = res["transaction_id"]

    donnees = {"cpm_trans_id": tx_id}
    corps_bytes = json.dumps(donnees).encode("utf-8")

    # 1. Test avec signature invalide -> 403 Forbidden
    resp_invalide = client_tenant.post(
        "/api/v1/cinetpay/webhook/",
        data=corps_bytes,
        content_type="application/json",
        headers={"x-token": "mauvaise_signature_123"},
    )
    assert resp_invalide.status_code == status.HTTP_403_FORBIDDEN
    assert resp_invalide.json()["status"] == "REJECTED"

    # 2. Test avec signature HMAC-SHA256 valide -> 200 OK
    signature_valide = hmac.new(
        b"cle_secrete_ultra_securisee",
        corps_bytes,
        hashlib.sha256,
    ).hexdigest()

    resp_valide = client_tenant.post(
        "/api/v1/cinetpay/webhook/",
        data=corps_bytes,
        content_type="application/json",
        headers={"x-token": signature_valide},
    )
    assert resp_valide.status_code == status.HTTP_200_OK
    assert resp_valide.json()["statut"] == "CONFIRME"


@pytest.mark.django_db
def test_webhook_cinetpay_site_id_invalide(client_tenant, entreprise_et_admin, settings):
    """Une notification avec un site_id erroné est rejetée."""
    settings.CINETPAY_SECRET_KEY = ""  # pas de HMAC pour tester isolément le site_id
    settings.CINETPAY_SITE_ID = "SITE_OFFICIEL_123"

    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    res = PaiementAbonnementService.initier_paiement(
        entreprise=entreprise,
        plan=plan,
        cycle="MENSUEL",
    )
    tx_id = res["transaction_id"]

    resp = client_tenant.post(
        "/api/v1/cinetpay/webhook/",
        data={
            "cpm_trans_id": tx_id,
            "cpm_site_id": "PIRATE_SITE",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["statut"] == "SITE_INVALIDE"


@pytest.mark.django_db
def test_reconciliation_automatique_tache_celery_et_commande(entreprise_et_admin):
    """La tâche Celery et la commande vérifient automatiquement les paiements en attente."""
    from apps.billing.tasks import verifier_paiements_en_attente

    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    # 1. Initialisation de deux paiements en attente
    res1 = PaiementAbonnementService.initier_paiement(entreprise=entreprise, plan=plan)
    tx1 = res1["transaction_id"]

    # Exécution de la commande CLI sur tx1
    call_command("verifier_paiements_cinetpay", transaction_id=tx1)

    with schema_context(get_public_schema_name()):
        p1 = PaiementAbonnement.objects.get(reference_transaction=tx1)
        assert p1.statut == PaiementAbonnement.Statut.CONFIRME

    # 2. Deuxième paiement testé par la tâche Celery de réconciliation
    res2 = PaiementAbonnementService.initier_paiement(entreprise=entreprise, plan=plan)
    tx2 = res2["transaction_id"]

    # Simuler que tx2 a été créée il y a 10 minutes pour être éligible au seuil
    with schema_context(get_public_schema_name()):
        PaiementAbonnement.objects.filter(reference_transaction=tx2).update(
            cree_le=timezone.now() - timedelta(minutes=10)
        )

    # Exécution de la tâche Celery
    stats = verifier_paiements_en_attente()
    assert stats["confirmes"] >= 1

    with schema_context(get_public_schema_name()):
        p2 = PaiementAbonnement.objects.get(reference_transaction=tx2)
        assert p2.statut == PaiementAbonnement.Statut.CONFIRME


@pytest.mark.django_db
def test_email_confirmation_envoye_sur_validation(entreprise_et_admin):
    """Un email de confirmation récapitulant la facture OHADA est émis lors de la validation."""
    from django.core import mail

    mail.outbox.clear()

    entreprise = entreprise_et_admin["entreprise"]
    plan = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    res = PaiementAbonnementService.initier_paiement(
        entreprise=entreprise,
        plan=plan,
        cycle="MENSUEL",
    )
    tx_id = res["transaction_id"]

    PaiementAbonnementService.traiter_notification_webhook(tx_id)

    # Vérification que l'email a été envoyé au contact de l'entreprise
    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert entreprise.email_contact in email.to
    assert "Confirmation de paiement" in email.subject
    assert "49000 FCFA" in email.body or "49 000 FCFA" in email.body or "49000" in email.body
    assert "Maître d'Œuvre" in email.body
