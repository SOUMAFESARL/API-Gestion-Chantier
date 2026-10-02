"""Tests d'intégration de l'architecture Catalogue Partagé et Droits d'usage."""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.catalogue.models import CatalogueModule, CataloguePermission, EntrepriseModule
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.tenants.models import Entreprise

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def client_tenant():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def admin_user(db):
    """Utilisateur administrateur tenant authentifié."""
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.catalogue.test@demo.ci",
            defaults={
                "nom": "Admin",
                "prenom": "Catalogue",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": False,
            },
        )
        user.role_global = RoleGlobal.ADMIN
        user.is_owner = False
        user.save()
        return user


@pytest.mark.django_db
class TestCataloguePartage:
    """Suite de vérification du catalogue partagé et des UUIDs."""

    def test_catalogue_module_identite_uuid(self, client_tenant, admin_user):
        """Vérifie que l'ID renvoyé au tenant correspond exactement à l'UUID canonique dans public."""
        with schema_context("public"):
            mod_projets_public = CatalogueModule.objects.get(code="projets")
            id_attendu = str(mod_projets_public.id)

            entreprise = Entreprise.objects.get(schema_name=SCHEMA)
            for m in CatalogueModule.objects.filter(est_actif=True):
                EntrepriseModule.objects.get_or_create(
                    entreprise=entreprise, module=m, defaults={"est_actif": True}
                )

        client_tenant.force_authenticate(user=admin_user)
        response = client_tenant.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        mod_projets = next(m for m in data if m["code"] == "projets")
        assert mod_projets["id"] == id_attendu

    def test_droit_usage_filtrage_module_inactif(self, client_tenant, admin_user):
        """Vérifie qu'un module désactivé dans EntrepriseModule est exclu de la liste tenant."""
        with schema_context("public"):
            entreprise = Entreprise.objects.get(schema_name=SCHEMA)
            for m in CatalogueModule.objects.filter(est_actif=True):
                EntrepriseModule.objects.get_or_create(
                    entreprise=entreprise, module=m, defaults={"est_actif": True}
                )

            mod_tiers = CatalogueModule.objects.get(code="tiers")
            em = EntrepriseModule.objects.get(entreprise=entreprise, module=mod_tiers)
            em.est_actif = False
            em.save()

        try:
            client_tenant.force_authenticate(user=admin_user)
            response = client_tenant.get("/api/v1/modules/")
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            codes = [m["code"] for m in data]
            assert "tiers" not in codes
            assert "projets" in codes
        finally:
            with schema_context("public"):
                em.est_actif = True
                em.save()

    def test_permissions_catalogue_m2m(self):
        """Vérifie l'association M2M entre CataloguePermission et CatalogueModule dans public."""
        with schema_context("public"):
            perm = CataloguePermission.objects.filter(code="ECRITURE").first()
            if perm:
                modules = list(perm.modules.all())
                assert len(modules) > 0
                for m in modules:
                    assert isinstance(m, CatalogueModule)
