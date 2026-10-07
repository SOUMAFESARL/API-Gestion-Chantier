"""Tests d'acceptation des permissions effectives (Règles A-04, A-06, A-12)."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.catalogue.models import CatalogueModule, CataloguePermission, EntrepriseModule
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.tenants.models import Entreprise

SCHEMA_TEST = "demo"
HOTE_TENANT = "demo.localhost"

pytestmark = pytest.mark.django_db


def test_a04_liste_cochee_exacte(client_tenant):
    """[A-04] Un rôle reçoit exactement la liste des permissions cochées dans permissions_catalogue."""
    with schema_context(SCHEMA_TEST):
        role_test, _ = Role.objects.get_or_create(
            code="TEST_EXACT",
            defaults={"libelle": "Rôle Test Exact", "est_systeme": False, "est_actif": True},
        )
        mod_projets = CatalogueModule.objects.get(code="projets")
        rmp, _ = RoleModulePermission.objects.get_or_create(
            role=role_test,
            module_catalogue=mod_projets,
            defaults={"niveau": 2},
        )
        p_lire = CataloguePermission.objects.filter(code="projets.lire").first()
        p_ecrire = CataloguePermission.objects.filter(code="projets.ecrire").first()
        if p_lire and p_ecrire:
            rmp.permissions_catalogue.set([p_lire, p_ecrire])

        user, _ = Utilisateur.tous_objets.get_or_create(
            email="test.exact@demo.ci",
            defaults={
                "nom": "User",
                "prenom": "Exact",
                "role_global": RoleGlobal.VISITEUR,
                "role_personnalise": role_test,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user.role_personnalise = role_test
        user.save()

    client_tenant.force_authenticate(user=user)
    rep = client_tenant.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = set(rep.data.get("permissions", []))
    assert "projets.lire" in perms
    assert "projets.ecrire" in perms
    # Pas de permission non attribuée sur le module
    assert "projets.creer" not in perms


def test_a04_valider_seul(client_tenant):
    """[A-04] Un rôle ayant seulement chantier.valider n'a ni chantier.lire ni chantier.rediger."""
    with schema_context(SCHEMA_TEST):
        role_test, _ = Role.objects.get_or_create(
            code="TEST_VALIDER_SEUL",
            defaults={"libelle": "Valideur Seul", "est_systeme": False, "est_actif": True},
        )
        mod_chantier = CatalogueModule.objects.get(code="chantier")
        rmp, _ = RoleModulePermission.objects.get_or_create(
            role=role_test,
            module_catalogue=mod_chantier,
            defaults={"niveau": 3},
        )
        p_valider = CataloguePermission.objects.filter(code="chantier.valider").first()
        if p_valider:
            rmp.permissions_catalogue.set([p_valider])

        user, _ = Utilisateur.tous_objets.get_or_create(
            email="valideur.seul@demo.ci",
            defaults={
                "nom": "User",
                "prenom": "Valideur",
                "role_global": RoleGlobal.VISITEUR,
                "role_personnalise": role_test,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user.role_personnalise = role_test
        user.save()

    client_tenant.force_authenticate(user=user)
    rep = client_tenant.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = set(rep.data.get("permissions", []))
    assert "chantier.valider" in perms
    assert "chantier.lire" not in perms
    assert "chantier.rediger" not in perms


def test_a04_effet_immediat_apres_modification(client_tenant):
    """[A-04] La modification d'une permission en base prend effet immédiatement à la requête suivante."""
    with schema_context(SCHEMA_TEST):
        role_test, _ = Role.objects.get_or_create(
            code="TEST_IMMEDIAT",
            defaults={"libelle": "Test Immédiat", "est_systeme": False, "est_actif": True},
        )
        mod_tiers = CatalogueModule.objects.get(code="tiers")
        rmp, _ = RoleModulePermission.objects.get_or_create(
            role=role_test,
            module_catalogue=mod_tiers,
        )
        p_lire = CataloguePermission.objects.filter(code="tiers.lire").first()
        p_ecrire = CataloguePermission.objects.filter(code="tiers.ecrire").first()
        if p_lire and p_ecrire:
            rmp.permissions_catalogue.set([p_lire, p_ecrire])

        user, _ = Utilisateur.tous_objets.get_or_create(
            email="user.immediat@demo.ci",
            defaults={
                "nom": "Immediat",
                "prenom": "User",
                "role_global": RoleGlobal.VISITEUR,
                "role_personnalise": role_test,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user.role_personnalise = role_test
        user.save()

    client_tenant.force_authenticate(user=user)
    rep1 = client_tenant.get("/api/v1/auth/profil/")
    assert "tiers.ecrire" in rep1.data.get("permissions", [])

    # Retrait de tiers.ecrire en base
    with schema_context(SCHEMA_TEST):
        if p_lire:
            rmp.permissions_catalogue.set([p_lire])

    rep2 = client_tenant.get("/api/v1/auth/profil/")
    assert "tiers.ecrire" not in rep2.data.get("permissions", [])
    assert "tiers.lire" in rep2.data.get("permissions", [])


def test_a06_module_desactive_supprime_permissions_effectives(client_tenant):
    """[A-06] Si un module est désactivé pour l'entreprise, aucune de ses permissions n'est effective."""
    with schema_context(SCHEMA_TEST):
        entreprise = Entreprise.objects.filter(schema_name=SCHEMA_TEST).first()
        mod_tiers = CatalogueModule.objects.get(code="tiers")
        em, _ = EntrepriseModule.objects.get_or_create(
            entreprise=entreprise,
            module=mod_tiers,
            defaults={"est_actif": True},
        )
        em.est_actif = False
        em.save()

        user, _ = Utilisateur.tous_objets.get_or_create(
            email="user.module.desactive@demo.ci",
            defaults={
                "nom": "Module",
                "prenom": "Desactive",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
            },
        )

    client_tenant.force_authenticate(user=user)
    rep = client_tenant.get("/api/v1/auth/profil/")
    assert rep.status_code == status.HTTP_200_OK
    perms = set(rep.data.get("permissions", []))
    for p in perms:
        assert not p.startswith("tiers."), f"La permission {p} d'un module désactivé ne doit pas être effective"

    # Restauration du module pour les tests suivants
    with schema_context(SCHEMA_TEST):
        em.est_actif = True
        em.save()


def test_a12_plus_de_plafond_modele_role(client_tenant):
    """[A-12] Les permissions cochées sont effectives sans être limitées par un quelconque plafond de modèle."""
    with schema_context(SCHEMA_TEST):
        role_mag = Role.objects.filter(code="MAG", supprime_le__isnull=True).first()
        if role_mag:
            mod_projets = CatalogueModule.objects.get(code="projets")
            rmp, _ = RoleModulePermission.objects.get_or_create(
                role=role_mag,
                module_catalogue=mod_projets,
            )
            p_lire = CataloguePermission.objects.filter(code="projets.lire").first()
            if p_lire:
                rmp.permissions_catalogue.add(p_lire)

            user_mag, _ = Utilisateur.tous_objets.get_or_create(
                email="user.mag.plafond@demo.ci",
                defaults={
                    "nom": "Magasinier",
                    "prenom": "Test",
                    "role_global": RoleGlobal.VISITEUR,
                    "role_personnalise": role_mag,
                    "statut": StatutUtilisateur.ACTIF,
                },
            )
            user_mag.role_personnalise = role_mag
            user_mag.save()

    if role_mag and p_lire:
        client_tenant.force_authenticate(user=user_mag)
        rep = client_tenant.get("/api/v1/auth/profil/")
        assert rep.status_code == status.HTTP_200_OK
        assert "projets.lire" in rep.data.get("permissions", [])
