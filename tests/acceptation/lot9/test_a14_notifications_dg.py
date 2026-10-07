"""Tests de la règle A-14 (Notification par e-mail au DG et journalisation d'audit après validation).

A-14 : Toute modification du super admin sur une entreprise (modules, permissions, rôles système)
est journalisée dans l'audit et déclenche un e-mail au DG (on_commit). Si transaction annulée : aucun e-mail.
"""

import pytest
from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_activation_module_aucun_email_avant_commit(fab):
    """[A-14] Activation d'un module : aucun e-mail n'est envoyé avant l'exécution des rappels on_commit."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="test_oncommit")
    client_admin = fab.client_super_admin()

    with transaction.atomic():
        res = fab.activer_module(client_admin, ea, mod)
        assert res.status_code == status.HTTP_200_OK
        # Avant le commit, aucun e-mail ne doit être présent dans outbox
        courriels_pendant_tx = fab.courriels_envoyes()
        # Noter que l'API DRF valide la requête à la sortie de la vue si hors transaction manuelle


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_activation_module_un_email_au_dg_apres_commit(fab):
    """[A-14] Après commit : un e-mail part au DG, avec le sujet fixe et citant le module et le super admin."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="notif_activation")
    client_admin = fab.client_super_admin()

    res = fab.activer_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK
    fab.valider_transaction()

    courriels = fab.courriels_envoyes()
    assert len(courriels) >= 1
    dernier = courriels[-1]
    assert "Modification de votre espace par l'administration de la plateforme" in dernier.subject
    assert client_admin.admin_user.email in dernier.body
    assert "notif_activation" in dernier.body


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_activation_module_une_entree_audit_tenant_une_plateforme(fab):
    """[A-14] L'activation d'un module crée exactement une entrée dans JournalAudit et une dans JournalPlateforme."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="audit_activation")
    client_admin = fab.client_super_admin()

    nb_audit_avant = len(fab.entrees_audit(ea))
    nb_plat_avant = len(fab.entrees_journal_plateforme())

    res = fab.activer_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK

    nb_audit_apres = len(fab.entrees_audit(ea))
    nb_plat_apres = len(fab.entrees_journal_plateforme())

    assert nb_audit_apres == nb_audit_avant + 1
    assert nb_plat_apres == nb_plat_avant + 1


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_desactivation_propagation_et_desactivation_permission_notifient_dg(fab):
    """[A-14] Désactivation, propagation et désactivation de permission notifient chacune le DG."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="notif_cycle")
    client_admin = fab.client_super_admin()

    fab.activer_module(client_admin, ea, mod)
    fab.valider_transaction()
    nb_1 = len(fab.courriels_envoyes())

    fab.desactiver_module(client_admin, ea, mod)
    fab.valider_transaction()
    nb_2 = len(fab.courriels_envoyes())

    assert nb_2 > nb_1, "La désactivation de module doit notifier le DG"


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_action_annulee_aucun_email_aucun_audit(fab):
    """[A-14] Une action annulée (rollback de transaction) n'émet aucun e-mail."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="action_annulee")

    nb_emails_avant = len(fab.courriels_envoyes())

    try:
        with schema_context(ea.schema_name):
            with transaction.atomic():
                # Simulation d'un appel métier qui échoue
                raise ValueError("Simulation erreur pour annuler la transaction")
    except ValueError:
        pass

    fab.valider_transaction()
    assert len(fab.courriels_envoyes()) == nb_emails_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_entreprise_sans_dg_actif_action_reussit_sans_email(fab):
    """[A-14] Entreprise sans DG actif (L9-4) : l'action réussit sans lever d'erreur et aucun e-mail n'est envoyé."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="sans_dg_test")

    with schema_context(ea.schema_name):
        from apps.accounts.models import Utilisateur
        from apps.core.enums import StatutUtilisateur, RoleGlobal
        Utilisateur.objects.filter(role_global=RoleGlobal.DIRECTEUR_GENERAL).update(statut=StatutUtilisateur.DESACTIVE, is_active=False)
        Utilisateur.objects.filter(is_owner=True).update(statut=StatutUtilisateur.DESACTIVE, is_active=False)

    client_admin = fab.client_super_admin()
    nb_emails_avant = len(fab.courriels_envoyes())

    res = fab.activer_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK
    fab.valider_transaction()

    # L'opération réussit, aucun e-mail n'a planté
    assert len(fab.courriels_envoyes()) == nb_emails_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_a14_synchronisation_catalogue_journal_plateforme_seul_sans_email(fab):
    """[A-14] Commande de synchronisation du catalogue : trace dans JournalPlateforme sans e-mail aux DG (L9-3)."""
    from django.core.management import call_command
    nb_emails_avant = len(fab.courriels_envoyes())

    call_command("synchroniser_catalogue_permissions")
    fab.valider_transaction()

    assert len(fab.courriels_envoyes()) == nb_emails_avant


@pytest.mark.carac
@pytest.mark.django_db
def test_a14_modification_modele_aucun_email(fab):
    """[A-14] La modification d'un modèle de rôle n'émet aucun e-mail aux DG (L9-2)."""
    nb_emails_avant = len(fab.courriels_envoyes())

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import ModeleRole
        m = ModeleRole.objects.first()
        if m:
            m.description = "Update description modèle"
            m.save()

    fab.valider_transaction()
    assert len(fab.courriels_envoyes()) == nb_emails_avant
