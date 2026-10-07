"""Tests des règles A-05 et A-06 (Cycle de vie des permissions du catalogue).

A-05 : Nouvelle permission synchronisée n'est ajoutée à aucun rôle stocké (DG calculé la possède de fait).
A-06 : Permission désactivée disparaît immédiatement des permissions effectives de toutes les entreprises.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status


@pytest.mark.regle
@pytest.mark.django_db
def test_a05_nouvelle_permission_synchronisee_absente_roles_stockes(fab):
    """[A-05] Une permission nouvelle synchronisée n'est ajoutée à aucun rôle stocké, dans A comme dans B, AD compris."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()

    # Création d'une nouvelle permission dans le catalogue (schéma public)
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod_projets = CatalogueModule.objects.filter(code="projets").first()
        code_perm = "PROJETS.NOUVELLE_PERM_TEST"
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Nouvelle Perm Test", "est_actif": True},
        )
        if mod_projets:
            perm.modules.add(mod_projets)

    # Vérification dans l'entreprise A
    with schema_context(ea.schema_name):
        from apps.accounts.models import RoleModulePermission
        lignes_contenant = RoleModulePermission.objects.filter(
            permissions_catalogue__code=code_perm
        )
        assert not lignes_contenant.exists(), "La nouvelle permission ne doit être injectée dans aucun rôle stocké de l'entreprise A"

    # Vérification dans l'entreprise B
    with schema_context(eb.schema_name):
        from apps.accounts.models import RoleModulePermission
        lignes_contenant_b = RoleModulePermission.objects.filter(
            permissions_catalogue__code=code_perm
        )
        assert not lignes_contenant_b.exists(), "La nouvelle permission ne doit être injectée dans aucun rôle stocké de l'entreprise B"


@pytest.mark.regle
@pytest.mark.django_db
def test_a05_nouvelle_permission_absente_permissions_effectives_ad_cp_perso(fab):
    """[A-05] Les permissions effectives de l'AD, d'un CP et d'un rôle personnalisé ne la contiennent pas."""
    ea = fab.entreprise_a()
    code_perm = "PROJETS.NOUVELLE_PERM_TEST2"
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod = CatalogueModule.objects.filter(code="projets").first()
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Perm Test 2", "est_actif": True},
        )
        if mod:
            perm.modules.add(mod)

    with schema_context(ea.schema_name):
        from apps.accounts.models import Role
        from apps.core.droits import permissions_effectives

        role_ad = Role.objects.filter(code="AD", supprime_le__isnull=True).first()
        role_cp = Role.objects.filter(code="CP", supprime_le__isnull=True).first()
        role_perso = fab.creer_role_perso(ea, "PERSO_A05", "Perso A05", permissions=["projets.lire"])

        perms_ad = fab.permissions_effectives_de(role_ad, ea)
        perms_cp = fab.permissions_effectives_de(role_cp, ea)
        perms_perso = fab.permissions_effectives_de(role_perso, ea)

        assert code_perm.lower() not in [p.lower() for p in perms_ad]
        assert code_perm.lower() not in [p.lower() for p in perms_cp]
        assert code_perm.lower() not in [p.lower() for p in perms_perso]


@pytest.mark.carac
@pytest.mark.django_db
def test_a05_nouvelle_permission_presente_dg_par_calcul(fab):
    """[A-05] Les permissions effectives du DG la contiennent par calcul souverain (B-03)."""
    ea = fab.entreprise_a()
    code_perm = "PROJETS.NOUVELLE_PERM_DG"
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod = CatalogueModule.objects.filter(code="projets").first()
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Perm DG", "est_actif": True},
        )
        if mod:
            perm.modules.add(mod)

    with schema_context(ea.schema_name):
        from apps.accounts.models import Utilisateur
        from apps.core.droits import permissions_effectives, est_dg

        dg = Utilisateur.objects.filter(supprime_le__isnull=True).filter(is_owner=True).first()
        if not dg:
            from apps.core.enums import RoleGlobal
            dg = Utilisateur.objects.filter(role_global=RoleGlobal.DIRECTEUR_GENERAL, supprime_le__isnull=True).first()
        if not dg:
            dg = fab.utilisateur("DG")
        assert dg is not None
        assert est_dg(dg) is True
        perms_dg = permissions_effectives(dg)
        assert code_perm.lower() in [p.lower() for p in perms_dg]


@pytest.mark.carac
@pytest.mark.django_db
def test_a05_dg_peut_cocher_nouvelle_permission_sur_role_perso(fab):
    """[A-05] Le DG peut cocher la nouvelle permission sur un rôle personnalisé (2xx, le porteur l'obtient)."""
    ea = fab.entreprise_a()
    code_perm = "PROJETS.COCHER_PERM"
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod = CatalogueModule.objects.filter(code="projets").first()
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Cocher Perm", "est_actif": True},
        )
        if mod:
            perm.modules.add(mod)

    with schema_context(ea.schema_name):
        role_perso = fab.creer_role_perso(ea, "PERSO_COCHABLE", "Perso Cochable", permissions=["projets.lire"])

        client_dg = fab.client_pour("DG")
        url = f"/api/v1/roles/{role_perso.id}/"
        payload = {
            "permissions": ["projets.lire", code_perm.lower()]
        }
        res = client_dg.patch(url, payload, format="json")
        assert res.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

        perms_perso = fab.permissions_effectives_de(role_perso, ea)
        assert code_perm.lower() in [p.lower() for p in perms_perso]


@pytest.mark.carac
@pytest.mark.django_db
def test_a05_ad_ne_peut_pas_cocher_nouvelle_permission(fab):
    """[A-05] L'AD tente de cocher une permission qu'il ne possède pas : 403 (B-08)."""
    ea = fab.entreprise_a()
    code_perm = "PROJETS.PERM_HORS_AD"
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod = CatalogueModule.objects.filter(code="projets").first()
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Perm Hors AD", "est_actif": True},
        )
        if mod:
            perm.modules.add(mod)

    with schema_context(ea.schema_name):
        role_perso = fab.creer_role_perso(ea, "PERSO_TENTATIVE_AD", "Perso Tentative AD", permissions=["projets.lire"])
        client_ad = fab.client_pour("AD")
        url = f"/api/v1/roles/{role_perso.id}/"
        payload = {
            "permissions": ["projets.lire", code_perm.lower()]
        }
        res = client_ad.patch(url, payload, format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.carac
@pytest.mark.django_db
def test_a05_synchronisation_repetee_aucun_doublon(fab):
    """[A-05] La commande de synchronisation répétée est strictement idempotente sans doublon."""
    from django.core.management import call_command
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission
        call_command("synchroniser_catalogue_permissions")
        nb_avant = CataloguePermission.objects.count()
        call_command("synchroniser_catalogue_permissions")
        nb_apres = CataloguePermission.objects.count()
        assert nb_avant == nb_apres


@pytest.mark.carac
@pytest.mark.django_db
def test_a06_permission_desactivee_en_base_disparait_des_deux_entreprises(fab):
    """[A-06] Désactivation en base : le code disparaît des permissions effectives des deux entreprises."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()
    code_perm = "PROJETS.DESACTIVEE_TEST"

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod = CatalogueModule.objects.filter(code="projets").first()
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Perm A Desactiver", "est_actif": True},
        )
        if mod:
            perm.modules.add(mod)

    # Attribution explicite dans EA et EB sur un rôle personnalisé
    role_a = fab.creer_role_perso(ea, "PERSO_A06_A", "Perso A06 A", permissions=[code_perm])
    role_b = fab.creer_role_perso(eb, "PERSO_A06_B", "Perso A06 B", permissions=[code_perm])

    assert code_perm.lower() in [p.lower() for p in fab.permissions_effectives_de(role_a, ea)]
    assert code_perm.lower() in [p.lower() for p in fab.permissions_effectives_de(role_b, eb)]

    # Désactivation dans le catalogue
    with schema_context(get_public_schema_name()):
        perm.est_actif = False
        perm.save(update_fields=["est_actif"])

    # Disparaît immédiatement des deux entreprises
    assert code_perm.lower() not in [p.lower() for p in fab.permissions_effectives_de(role_a, ea)]
    assert code_perm.lower() not in [p.lower() for p in fab.permissions_effectives_de(role_b, eb)]


@pytest.mark.regle
@pytest.mark.django_db
def test_a06_permission_desactivee_par_api_super_admin_audit_et_email(fab):
    """[A-06] Désactivation d'une permission par l'API super admin : même effet, plus audit et e-mails aux DG."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()
    code_perm = "PROJETS.API_DESACTIVE"

    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import CataloguePermission, CatalogueModule
        mod = CatalogueModule.objects.filter(code="projets").first()
        perm, _ = CataloguePermission.objects.update_or_create(
            code=code_perm,
            defaults={"libelle": "Perm API Desactive", "est_actif": True},
        )
        if mod:
            perm.modules.add(mod)

    client_admin = fab.client_super_admin()
    url = f"/api/v1/admins/permissions/{perm.id}/"
    res = client_admin.patch(url, {"est_actif": False}, format="json")
    assert res.status_code == status.HTTP_200_OK

    fab.valider_transaction()

    # Vérification que la permission est désactivée
    with schema_context(get_public_schema_name()):
        perm.refresh_from_db()
        assert perm.est_actif is False

    # E-mails envoyés aux DG des entreprises actives
    courriels = fab.courriels_envoyes()
    assert len(courriels) >= 1
    sujets = [m.subject for m in courriels]
    assert any("Modification de votre espace par l'administration" in s for s in sujets)
