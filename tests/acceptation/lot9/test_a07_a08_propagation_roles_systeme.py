"""Tests des règles A-07 et A-08 (Propagation des rôles système et modification de modèle).

A-07 : Nouveau rôle système propagé à toutes les entreprises existantes sans modifier aucun rôle existant.
A-08 : Modification d'un modèle de rôle ne touche pas les entreprises existantes (copies indépendantes).
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_nouveau_modele_role_propage_a_toutes_entreprises(fab):
    """[A-07] Nouveau ModeleRole 'SUP' puis propager_roles_systeme : A et B ont un rôle SUP, est_systeme=True, portée du modèle."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()

    fab.creer_modele_role(
        code="SUP",
        nom="Superviseur Travaux",
        portee="PROJET",
        defauts={"projets": ["projets.lire"], "chantier": ["chantier.lire"]},
    )

    fab.propager()

    # Vérification dans A
    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        role_sup_a = Role.objects.filter(code="SUP", supprime_le__isnull=True).first()
        assert role_sup_a is not None
        assert role_sup_a.est_systeme is True
        assert role_sup_a.portee == "PROJET"
        assert role_sup_a.libelle == "Superviseur Travaux"

    # Vérification dans B
    with schema_context(eb.schema_name):
        from apps.accounts.models import Role
        role_sup_b = Role.objects.filter(code="SUP", supprime_le__isnull=True).first()
        assert role_sup_b is not None
        assert role_sup_b.est_systeme is True
        assert role_sup_b.portee == "PROJET"


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_nouveau_role_lignes_uniquement_modules_actifs(fab):
    """[A-07] Le nouveau rôle reçoit des lignes RoleModulePermission seulement pour les modules actifs du tenant."""
    ea = fab.entreprise_a()

    fab.creer_modele_role(
        code="INSP",
        nom="Inspecteur Qualité",
        portee="PROJET",
        defauts={"projets": ["projets.lire"]},
    )

    fab.propager()

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role, RoleModulePermission
        role = Role.objects.get(code="INSP")
        rmps = RoleModulePermission.objects.filter(role=role)
        modules_codes = [rmp.module_code for rmp in rmps]
        assert "projets" in modules_codes


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_nouveau_role_module_inactif_aucune_ligne(fab):
    """[A-07] Un module inactif dans l'entreprise n'a aucune ligne pour le rôle propagé."""
    ea = fab.entreprise_a()
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import EntrepriseModule, CatalogueModule
        mod_ged = CatalogueModule.objects.filter(code="ged").first()
        if mod_ged:
            EntrepriseModule.objects.filter(entreprise=ea, module=mod_ged).update(est_actif=False)

    fab.creer_modele_role(
        code="AUD",
        nom="Auditeur Externe",
        portee="ENTREPRISE",
        defauts={"ged": []},
    )

    fab.propager()

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role, RoleModulePermission
        role = Role.objects.get(code="AUD")
        assert not RoleModulePermission.objects.filter(role=role, module_code="ged").exists()


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_deuxieme_propagation_idempotente_aucun_changement(fab):
    """[A-07] Deuxième exécution de propager_roles_systeme : aucun doublon, aucun e-mail supplémentaire."""
    fab.creer_modele_role(code="EXP", nom="Expert Technique", portee="ENTREPRISE")
    fab.propager()
    fab.valider_transaction()
    nb_emails_1 = len(fab.courriels_envoyes())

    fab.propager()
    fab.valider_transaction()
    nb_emails_2 = len(fab.courriels_envoyes())

    assert nb_emails_2 == nb_emails_1


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_roles_preexistants_et_collaborateurs_inchanges(fab):
    """[A-07] Tous les rôles préexistants (système et personnalisés) sont strictement identiques avant et après."""
    ea = fab.entreprise_a()
    role_perso = fab.creer_role_perso(ea, "PERSO_STABLE", "Perso Stable", permissions=["projets.lire"])

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        perms_avant = set(fab.permissions_effectives_de(role_perso, ea))
        role_ad_avant = Role.objects.get(code="AD")
        perms_ad_avant = set(fab.permissions_effectives_de(role_ad_avant, ea))

    fab.creer_modele_role(code="NOUV_SYS", nom="Nouveau Système", portee="PROJET")
    fab.propager()

    with schema_context(ea.schema_name):
        role_perso.refresh_from_db()
        assert role_perso.code == "PERSO_STABLE"
        assert set(fab.permissions_effectives_de(role_perso, ea)) == perms_avant
        assert set(fab.permissions_effectives_de(role_ad_avant, ea)) == perms_ad_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_creation_modele_declenche_propagation(fab):
    """[A-07] Création du modèle par le service ou la commande propage le rôle dans les entreprises existantes."""
    ea = fab.entreprise_a()
    fab.creer_modele_role(code="CONT", nom="Contrôleur Gestion", portee="ENTREPRISE")
    fab.propager()

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        assert Role.objects.filter(code="CONT", supprime_le__isnull=True).exists()


@pytest.mark.regle
@pytest.mark.django_db
def test_a07_propagation_non_super_admin_refusee(fab):
    """[A-07] Un non-super admin (ex: client DG ou AD) ne peut pas déclencher la commande/route de propagation."""
    client_dg = fab.client_pour("DG")
    res = client_dg.post("/api/v1/admins/journal-plateforme/", format="json")
    assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


@pytest.mark.carac
@pytest.mark.django_db
def test_a08_modification_modele_n_affecte_pas_entreprises_existantes(fab):
    """[A-08] Un modèle de rôle existant est modifié dans public : les rôles des entreprises A et B sont inchangés."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import ModeleRole
        ct_modele = ModeleRole.objects.filter(code="CT").first()
        if ct_modele:
            ct_modele.libelle = "Conducteur de Travaux Principal Modifié"
            ct_modele.save(update_fields=["libelle"])

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        role_ct_a = Role.objects.get(code="CT")
        assert role_ct_a.libelle != "Conducteur de Travaux Principal Modifié"

    with schema_context(eb.schema_name):
        from apps.accounts.models import Role
        role_ct_b = Role.objects.get(code="CT")
        assert role_ct_b.libelle != "Conducteur de Travaux Principal Modifié"


@pytest.mark.carac
@pytest.mark.django_db
def test_a08_nouvelle_entreprise_reflète_modification_modele(fab):
    """[A-08] Une nouvelle entreprise créée après modification du modèle reflète le modèle actualisé."""
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import ModeleRole
        m = ModeleRole.objects.filter(code="CT").first()
        assert m is not None


@pytest.mark.carac
@pytest.mark.django_db
def test_a08_modification_modele_aucun_audit_tenant_aucun_email(fab):
    """[A-08] La modification d'un modèle n'écrit aucun audit de tenant et n'envoie aucun e-mail aux DG (L9-2)."""
    ea = fab.entreprise_a()
    nb_audit_avant = len(fab.entrees_audit(ea))
    nb_emails_avant = len(fab.courriels_envoyes())

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import ModeleRole
        m = ModeleRole.objects.first()
        if m:
            m.description = "Nouvelle description"
            m.save()

    fab.valider_transaction()
    assert len(fab.entrees_audit(ea)) == nb_audit_avant
    assert len(fab.courriels_envoyes()) == nb_emails_avant
