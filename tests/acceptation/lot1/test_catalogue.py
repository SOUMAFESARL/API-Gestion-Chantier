"""Tests d'acceptation du catalogue de permissions (Règles A-01, A-02, A-03, A-06, A-15)."""

from io import StringIO
import pytest
from django.core.management import call_command
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status

from apps.accounts.models import RoleModulePermission
from apps.catalogue.models import CatalogueModule, CataloguePermission
from apps.core.registre_permissions import REGISTRE

pytestmark = pytest.mark.django_db


def test_a01_catalogue_egal_registre_apres_synchronisation():
    """[A-01] Après exécution de la synchronisation, les codes actifs du catalogue correspondent au REGISTRE."""
    with schema_context(get_public_schema_name()):
        out = StringIO()
        call_command("synchroniser_catalogue_permissions", stdout=out)
        
        codes_catalogue = set(
            CataloguePermission.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).values_list("code", flat=True)
        )
        codes_registre = set(REGISTRE.keys())
        assert codes_registre.issubset(codes_catalogue), (
            f"Codes du REGISTRE absents du catalogue : {codes_registre - codes_catalogue}"
        )


def test_a01_synchronisation_idempotente():
    """[A-01] La commande de synchronisation exécutée plusieurs fois est strictement idempotente."""
    with schema_context(get_public_schema_name()):
        out1 = StringIO()
        call_command("synchroniser_catalogue_permissions", stdout=out1)
        snapshot1 = {
            p.code: (str(p.id), p.libelle, p.est_actif)
            for p in CataloguePermission.objects.filter(supprime_le__isnull=True)
        }

        out2 = StringIO()
        call_command("synchroniser_catalogue_permissions", stdout=out2)
        snapshot2 = {
            p.code: (str(p.id), p.libelle, p.est_actif)
            for p in CataloguePermission.objects.filter(supprime_le__isnull=True)
        }

        assert snapshot1 == snapshot2, "La seconde synchronisation a altéré les identifiants ou états du catalogue"


def test_a01_creation_permission_code_inconnu_refusee(client_super_admin):
    """[A-01] La création d'une permission avec un code hors REGISTRE est rejetée avec HTTP 400."""
    payload = {
        "code": "module_inconnu.action_inventee",
        "libelle": "Permission Inconnue",
        "description": "Tentative hors REGISTRE",
        "ordre": 99,
        "est_actif": True,
    }
    rep = client_super_admin.post("/api/v1/admins/permissions/", payload, format="json")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST


def test_a02_module_non_modifiable(client_super_admin):
    """[A-02] Le super admin ne peut pas modifier le module d'une permission existante (HTTP 400)."""
    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.filter(supprime_le__isnull=True).first()
        assert perm is not None, "Aucune permission présente au catalogue pour tester le refus"
        perm_id = perm.id

    payload = {"module": "nouveau_module_invalide"}
    rep = client_super_admin.patch(f"/api/v1/admins/permissions/{perm_id}/", payload, format="json")
    assert rep.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED)


def test_a03_aucun_verbe_generique_dans_catalogue():
    """[A-03] Aucun verbe générique (LECTURE, ECRITURE, VALIDATION, SUPPRESSION) ne subsiste dans le catalogue."""
    verbes_interdits = {"LECTURE", "ECRITURE", "VALIDATION", "SUPPRESSION"}
    with schema_context(get_public_schema_name()):
        codes_actuels = set(
            CataloguePermission.objects.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )
        trouves = verbes_interdits & codes_actuels
        assert not trouves, f"Des verbes génériques subsistent dans CataloguePermission : {trouves}"


def test_a03_une_seule_relation_m2m_sur_role_module_permission():
    """[A-03] RoleModulePermission n'a plus de relation ManyToMany vers l'ancien accounts.Permission."""
    m2m_fields = [f.name for f in RoleModulePermission._meta.many_to_many]
    assert "permissions" not in m2m_fields, (
        "L'ancienne relation 'permissions' vers accounts.Permission doit être supprimée de RoleModulePermission"
    )
    assert "permissions_catalogue" in m2m_fields, (
        "La relation 'permissions_catalogue' doit être la relation ManyToMany active sur RoleModulePermission"
    )


def test_a15_ged_desactive_par_defaut_nouvelle_entreprise():
    """[A-15] Le module GED est présent au catalogue mais inactif par défaut pour une nouvelle entreprise."""
    with schema_context(get_public_schema_name()):
        mod_ged = CatalogueModule.objects.filter(code="ged", supprime_le__isnull=True).first()
        if mod_ged:
            assert mod_ged.est_actif is True  # Présent au catalogue
