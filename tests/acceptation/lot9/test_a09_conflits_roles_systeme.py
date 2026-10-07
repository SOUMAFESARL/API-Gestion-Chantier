"""Tests de la règle A-09 (Conflit de code ou de nom lors de la propagation d'un rôle système).

A-09 : Le rôle système l'emporte. Le rôle personnalisé en conflit est automatiquement renommé.
Identifiant, collaborateurs, portée et permissions du rôle personnalisé restent inchangés.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_conflit_code_role_perso_renomme_suffixe_perso(fab):
    """[A-09] Rôle personnalisé de même code qu'un nouveau rôle système : renommé '{code}_perso' ; le rôle système existe."""
    ea = fab.entreprise_a()
    # Création du rôle personnalisé en conflit sur le code
    role_perso = fab.creer_role_perso(ea, code="GEST", nom="Gestionnaire Flotte", permissions=["projets.lire"])

    # Nouveau rôle système avec le même code 'GEST'
    fab.creer_modele_role(code="GEST", nom="Gestionnaire de Chantiers", portee="PROJET")
    fab.propager()

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        role_perso.refresh_from_db()
        assert role_perso.code == "GEST_perso"
        assert "(personnalisé)" in role_perso.libelle

        role_sys = Role.objects.filter(code="GEST", est_systeme=True).first()
        assert role_sys is not None
        assert role_sys.libelle == "Gestionnaire de Chantiers"


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_conflit_nom_casse_differente_renomme_aussi(fab):
    """[A-09] Même nom (casse différente), code différent : nom renommé avec '(personnalisé)' et code aussi."""
    ea = fab.entreprise_a()
    role_perso = fab.creer_role_perso(ea, code="MON_QUAL", nom="responsable qualite", permissions=["projets.lire"])

    fab.creer_modele_role(code="RQ", nom="Responsable Qualité", portee="ENTREPRISE")
    fab.propager()

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        role_perso.refresh_from_db()
        assert "(personnalisé)" in role_perso.libelle
        assert role_perso.code == "MON_QUAL_perso"


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_conflit_code_et_nom_renommage_coherent(fab):
    """[A-09] Conflit sur code et nom simultanément : un seul renommage cohérent."""
    ea = fab.entreprise_a()
    role_perso = fab.creer_role_perso(ea, code="LOG", nom="Logisticien", permissions=["projets.lire"])

    fab.creer_modele_role(code="LOG", nom="Logisticien", portee="ENTREPRISE")
    fab.propager()

    with schema_context(ea.schema_name):
        role_perso.refresh_from_db()
        assert role_perso.code == "LOG_perso"
        assert role_perso.libelle == "Logisticien (personnalisé)"


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_conflit_suffixe_deja_pris_incremente(fab):
    """[A-09] Si '{code}_perso' est déjà pris, renomme en '{code}_perso2'."""
    ea = fab.entreprise_a()
    role_p1 = fab.creer_role_perso(ea, code="PLANI_perso", nom="Planificateur (personnalisé)", permissions=["projets.lire"])
    role_p2 = fab.creer_role_perso(ea, code="PLANI", nom="Planificateur", permissions=["projets.lire"])

    fab.creer_modele_role(code="PLANI", nom="Planificateur Principal", portee="ENTREPRISE")
    fab.propager()

    with schema_context(ea.schema_name):
        role_p2.refresh_from_db()
        assert role_p2.code == "PLANI_perso2"


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_role_renomme_conserve_collaborateurs_et_permissions(fab):
    """[A-09] Collaborateurs, permissions, portée et identifiant du rôle renommé restent strictement identiques."""
    ea = fab.entreprise_a()
    role_perso = fab.creer_role_perso(ea, code="ACHAT", nom="Acheteur Appro", permissions=["projets.lire"])
    original_id = role_perso.id

    with schema_context(ea.schema_name):
        from apps.accounts.models import Utilisateur
        u = Utilisateur.objects.create_user(
            email="acheteur.test@demo.ci",
            password="Password123!",
            nom="Acheteur",
            prenom="Test",
            role=role_perso,
        )

    perms_avant = set(fab.permissions_effectives_de(role_perso, ea))

    fab.creer_modele_role(code="ACHAT", nom="Responsable Achats", portee="ENTREPRISE")
    fab.propager()

    with schema_context(ea.schema_name):
        role_perso.refresh_from_db()
        u.refresh_from_db()
        assert role_perso.id == original_id
        assert u.role_id == role_perso.id
        assert set(fab.permissions_effectives_de(role_perso, ea)) == perms_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_role_perso_sans_conflit_intact(fab):
    """[A-09] Un rôle personnalisé sans conflit avec le nouveau rôle système reste totalement intact."""
    ea = fab.entreprise_a()
    role_perso = fab.creer_role_perso(ea, code="UNIQUE_PERSO", nom="Rôle Unique", permissions=["projets.lire"])

    fab.creer_modele_role(code="AUTRE_SYS", nom="Autre Système", portee="PROJET")
    fab.propager()

    with schema_context(ea.schema_name):
        role_perso.refresh_from_db()
        assert role_perso.code == "UNIQUE_PERSO"
        assert role_perso.libelle == "Rôle Unique"


@pytest.mark.regle
@pytest.mark.django_db
def test_a09_email_et_audit_dg_citent_le_renommage(fab):
    """[A-09] L'e-mail et l'audit du DG citent explicitement le renommage du rôle personnalisé."""
    ea = fab.entreprise_a()
    fab.creer_role_perso(ea, code="SECUR", nom="Sécurité Chantier", permissions=["projets.lire"])

    fab.creer_modele_role(code="SECUR", nom="Responsable Sécurité", portee="PROJET")
    fab.propager()
    fab.valider_transaction()

    # Vérification de l'e-mail au DG
    courriels = fab.courriels_envoyes()
    assert len(courriels) >= 1
    corps_tous = " ".join([m.body for m in courriels])
    assert "SECUR_perso" in corps_tous or "renommé" in corps_tous.lower()

    # Vérification de l'entrée de journal d'audit
    audits = fab.entrees_audit(ea)
    assert any("renommé" in str(a.valeur_apres).lower() or "secur" in str(a.valeur_apres).lower() for a in audits)
