"""Tests des règles A-10 et A-11 (Activation et désactivation d'un module par entreprise).

A-10 : Module désactivé : permissions ignorées pour toute l'entreprise, lignes en base intactes.
A-11 : Activation d'un module : copie unique (rôles système = défauts, rôles personnalisés = ligne vide).
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status


@pytest.mark.carac
@pytest.mark.django_db
def test_a10_module_desactive_permissions_ignorees(fab):
    """[A-10] Module désactivé : les permissions sont ignorées pour tous les rôles de l'entreprise, DG compris."""
    ea = fab.entreprise_a()
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import EntrepriseModule, CatalogueModule
        mod_chantier = CatalogueModule.objects.filter(code="chantier").first()
        assert mod_chantier is not None
        em, _ = EntrepriseModule.objects.get_or_create(entreprise=ea, module=mod_chantier)
        em.est_actif = False
        em.save(update_fields=["est_actif"])

    with schema_context(ea.schema_name):
        from apps.accounts.models import Utilisateur
        from apps.core.droits import permissions_effectives
        dg = Utilisateur.objects.filter(is_owner=True, supprime_le__isnull=True).first()
        perms = permissions_effectives(dg)
        assert not any(p.startswith("chantier.") for p in perms)

    # Nettoyage
    with schema_context(get_public_schema_name()):
        em.est_actif = True
        em.save(update_fields=["est_actif"])


@pytest.mark.carac
@pytest.mark.django_db
def test_a10_module_desactive_lignes_role_module_permission_intactes(fab):
    """[A-10] Désactivation d'un module : les lignes RoleModulePermission restent intactes en base."""
    ea = fab.entreprise_a()
    with schema_context(ea.schema_name):
        from apps.accounts.models import RoleModulePermission
        nb_rmp_avant = RoleModulePermission.objects.filter(module_catalogue__code="chantier").count()

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import EntrepriseModule, CatalogueModule
        mod = CatalogueModule.objects.get(code="chantier")
        EntrepriseModule.objects.filter(entreprise=ea, module=mod).update(est_actif=False)

    with schema_context(ea.schema_name):
        nb_rmp_apres = RoleModulePermission.objects.filter(module_catalogue__code="chantier").count()
        assert nb_rmp_apres == nb_rmp_avant

    with schema_context(get_public_schema_name()):
        EntrepriseModule.objects.filter(entreprise=ea, module=mod).update(est_actif=True)


@pytest.mark.regle
@pytest.mark.django_db
def test_a10_reactivation_retrouve_exactement_memes_permissions(fab):
    """[A-10] À la réactivation après modification d'un rôle personnalisé : retrouve les mêmes permissions qu'avant."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="qualite", permissions=["qualite.audit"])
    client_admin = fab.client_super_admin()

    # Activation initiale
    fab.activer_module(client_admin, ea, mod)
    role_perso = fab.creer_role_perso(ea, "PERSO_QUAL", "Perso Qualité", permissions=["qualite.audit"])

    assert "qualite.audit" in fab.permissions_effectives_de(role_perso, ea)

    # Désactivation
    fab.desactiver_module(client_admin, ea, mod)
    assert "qualite.audit" not in fab.permissions_effectives_de(role_perso, ea)

    # Réactivation : retrouve immédiatement sans recopie
    fab.activer_module(client_admin, ea, mod)
    assert "qualite.audit" in fab.permissions_effectives_de(role_perso, ea)


@pytest.mark.regle
@pytest.mark.django_db
def test_a10_desactivation_par_api_seul_tenant_cible_affecte(fab):
    """[A-10] Désactivation par l'API super admin : 200, seule l'entreprise cible est affectée, B reste intacte."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()
    mod = fab.creer_module_catalogue(code="securite", permissions=["securite.voir"])
    client_admin = fab.client_super_admin()

    fab.activer_module(client_admin, ea, mod)
    fab.activer_module(client_admin, eb, mod)

    res = fab.desactiver_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import EntrepriseModule
        em_a = EntrepriseModule.objects.filter(entreprise=ea, module=mod).first()
        em_b = EntrepriseModule.objects.filter(entreprise=eb, module=mod).first()
        assert em_a.est_actif is False
        assert em_b.est_actif is True


@pytest.mark.regle
@pytest.mark.django_db
def test_a10_desactiver_module_deja_inactif_sans_changement_sans_email(fab):
    """[A-10] Désactiver un module déjà inactif renvoie 200, aucun changement et aucun e-mail (L9-7)."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="inactif_test")
    client_admin = fab.client_super_admin()

    fab.valider_transaction()
    nb_emails_avant = len(fab.courriels_envoyes())

    res = fab.desactiver_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK
    fab.valider_transaction()

    assert len(fab.courriels_envoyes()) == nb_emails_avant


@pytest.mark.carac
@pytest.mark.django_db
def test_a11_avant_activation_aucune_ligne_module(fab):
    """[A-11] Avant l'activation d'un module, aucune ligne RoleModulePermission n'existe pour ce module dans EA."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="nouveau_mod", permissions=["nouveau_mod.action"])
    lignes = fab.lignes_du_module(ea, mod)
    assert len(lignes) == 0


@pytest.mark.regle
@pytest.mark.django_db
def test_a11_activation_api_chaque_role_non_dg_a_ligne_explicite(fab):
    """[A-11] Activation par l'API : 200 ; chaque rôle non DG a une ligne explicite en base pour ce module."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="materiel", permissions=["materiel.voir"])
    client_admin = fab.client_super_admin()

    res = fab.activer_module(client_admin, ea, mod)
    assert res.status_code == status.HTTP_200_OK

    lignes = fab.lignes_du_module(ea, mod)
    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        roles_non_dg = Role.objects.exclude(code__in=["DG", "DIRECTEUR_GENERAL"]).filter(supprime_le__isnull=True)
        roles_ids_lignes = {rmp.role_id for rmp in lignes}
        for r in roles_non_dg:
            assert r.id in roles_ids_lignes, f"Le rôle {r.code} doit avoir une ligne explicite pour le module activé"


@pytest.mark.regle
@pytest.mark.django_db
def test_a11_roles_systeme_recoivent_defauts_et_perso_ligne_vide(fab):
    """[A-11] Les rôles système reçoivent les permissions par défaut du modèle ; les rôles personnalisés reçoivent une ligne vide."""
    ea = fab.entreprise_a()
    role_perso = fab.creer_role_perso(ea, "PERSO_A11", "Perso A11")

    mod = fab.creer_module_catalogue(
        code="maintenance",
        permissions=["maintenance.lire", "maintenance.ecrire"],
        defauts_par_role={"CP": ["maintenance.lire"]}
    )
    client_admin = fab.client_super_admin()
    fab.activer_module(client_admin, ea, mod)

    with schema_context(ea.schema_name):
        from apps.accounts.models import RoleModulePermission, Role
        rmp_perso = RoleModulePermission.objects.filter(role=role_perso, module_code="maintenance").first()
        assert rmp_perso is not None
        assert rmp_perso.permissions_catalogue.count() == 0, "Le rôle personnalisé doit recevoir une ligne vide explicite"

        role_cp = Role.objects.get(code="CP")
        rmp_cp = RoleModulePermission.objects.filter(role=role_cp, module_code="maintenance").first()
        assert rmp_cp is not None


@pytest.mark.regle
@pytest.mark.django_db
def test_a11_activation_n_affecte_pas_autre_entreprise(fab):
    """[A-11] L'activation d'un module pour l'entreprise A ne crée aucune ligne dans l'entreprise B."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()
    mod = fab.creer_module_catalogue(code="energie", permissions=["energie.voir"])
    client_admin = fab.client_super_admin()

    fab.activer_module(client_admin, ea, mod)
    assert len(fab.lignes_du_module(eb, mod)) == 0


@pytest.mark.regle
@pytest.mark.django_db
def test_a11_suppression_defauts_modele_apres_activation_permissions_inchangées(fab):
    """[A-11] Rien n'est lu dans le modèle à l'exécution : supprimer les défauts du modèle ne change rien."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(
        code="telecom",
        permissions=["telecom.voir"],
        defauts_par_role={"CP": ["telecom.voir"]}
    )
    client_admin = fab.client_super_admin()
    fab.activer_module(client_admin, ea, mod)

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        role_cp = Role.objects.get(code="CP")
        perms_avant = set(fab.permissions_effectives_de(role_cp, ea))

    # Suppression du défaut dans le modèle public
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import ModeleRoleModule
        ModeleRoleModule.objects.filter(module_code="telecom").delete()

    with schema_context(ea.schema_name):
        perms_apres = set(fab.permissions_effectives_de(role_cp, ea))
        assert perms_apres == perms_avant


@pytest.mark.carac
@pytest.mark.django_db
def test_a11_modification_defauts_apres_activation_permissions_inchangées(fab):
    """[A-11] Modifier les défauts du modèle après activation n'affecte pas l'entreprise existante (A-12)."""
    ea = fab.entreprise_a()
    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        role_ad = Role.objects.get(code="AD")
        perms_avant = set(fab.permissions_effectives_de(role_ad, ea))

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import ModeleRoleModule
        mrm = ModeleRoleModule.objects.filter(modele_role__code="AD").first()
        if mrm:
            mrm.description = "Test modification"
            mrm.save()

    with schema_context(ea.schema_name):
        perms_apres = set(fab.permissions_effectives_de(role_ad, ea))
        assert perms_apres == perms_avant


@pytest.mark.regle
@pytest.mark.django_db
def test_a11_activer_deux_fois_idempotent_un_seul_email(fab):
    """[A-11] Activer deux fois un module : strictement idempotent, un seul e-mail émis."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="logistique")
    client_admin = fab.client_super_admin()

    res1 = fab.activer_module(client_admin, ea, mod)
    assert res1.status_code == status.HTTP_200_OK
    fab.valider_transaction()
    nb_emails_1 = len(fab.courriels_envoyes())

    res2 = fab.activer_module(client_admin, ea, mod)
    assert res2.status_code == status.HTTP_200_OK
    fab.valider_transaction()
    nb_emails_2 = len(fab.courriels_envoyes())

    assert nb_emails_2 == nb_emails_1


@pytest.mark.regle
@pytest.mark.django_db
def test_a11_role_cree_apres_desactivation_puis_reactivation(fab):
    """[A-11] Rôle créé pendant que le module est inactif : reçoit sa ligne lors de la réactivation du module."""
    ea = fab.entreprise_a()
    mod = fab.creer_module_catalogue(code="environnement")
    client_admin = fab.client_super_admin()

    fab.activer_module(client_admin, ea, mod)
    fab.desactiver_module(client_admin, ea, mod)

    role_nouveau = fab.creer_role_perso(ea, "PERSO_ENV", "Perso Environnement")

    fab.activer_module(client_admin, ea, mod)

    with schema_context(ea.schema_name):
        from apps.accounts.models import RoleModulePermission
        assert RoleModulePermission.objects.filter(role=role_nouveau, module_code="environnement").exists()
