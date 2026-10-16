"""Tests B2 du chantier « droits » — Le service du back-office travaille sur le catalogue."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.catalogue.models import CatalogueModule, CataloguePermission
from apps.core.enums import RoleGlobal, StatutUtilisateur

pytestmark = pytest.mark.django_db

HOTE = "localhost"


@pytest.fixture
def superviseur_client(settings):
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="superviseur.b2@ccd-digital.ci").delete()
        superviseur = Utilisateur.objects.create_superuser(
            email="superviseur.b2@ccd-digital.ci",
            password="MotDePasse12345!",
            nom="Superviseur",
            prenom="B2",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
    client = APIClient(HTTP_HOST=HOTE)
    client.force_authenticate(superviseur)
    return client


def test_patch_permissions_module_avec_ses_codes_reels(superviseur_client):
    """PATCH /admins/modules/{projets}/permissions/ avec les codes réels -> 200, codes conservés."""
    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)
        codes = list(
            mod_projets.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )
        assert len(codes) > 0

    rep = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/permissions/",
        {"permissions": codes},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content
    assert sorted(rep.json()["permissions_codes"]) == sorted(codes)


def test_codes_compares_sans_casse(superviseur_client):
    """["PROJETS.LIRE", "projets.creer"] -> 200, codes renvoyés en minuscules."""
    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)

    rep = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/permissions/",
        {"permissions": ["PROJETS.LIRE", "projets.creer"]},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content
    assert sorted(rep.json()["permissions_codes"]) == ["projets.creer", "projets.lire"]


def test_code_inconnu_refuse(superviseur_client):
    """["projets.inexistante"] -> 400, message §2.4 mot pour mot, module inchangé."""
    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)
        codes_avant = set(
            mod_projets.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )

    rep = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/permissions/",
        {"permissions": ["projets.inexistante"]},
        format="json",
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST, rep.content
    assert "Permission inconnue : « projets.inexistante »." in str(rep.json())

    with schema_context(get_public_schema_name()):
        mod_projets.refresh_from_db()
        assert (
            set(
                mod_projets.permissions.filter(supprime_le__isnull=True).values_list(
                    "code", flat=True
                )
            )
            == codes_avant
        )


def test_prefixe_d_un_autre_module_refuse(superviseur_client):
    """projets + ["chantier.lire"] -> 400, message §2.3, module inchangé."""
    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)
        codes_avant = set(
            mod_projets.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )

    rep = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/permissions/",
        {"permissions": ["chantier.lire"]},
        format="json",
    )
    assert rep.status_code == status.HTTP_400_BAD_REQUEST, rep.content
    assert (
        "La permission « chantier.lire » appartient au module « chantier » : "
        "elle ne peut pas être rattachée au module « projets »."
        in str(rep.json())
    )

    with schema_context(get_public_schema_name()):
        mod_projets.refresh_from_db()
        assert (
            set(
                mod_projets.permissions.filter(supprime_le__isnull=True).values_list(
                    "code", flat=True
                )
            )
            == codes_avant
        )


def test_retrait_revoque_les_roles(schema_demo, superviseur_client):
    """Le CP perd la permission lors du retrait du module et ne la récupère pas lors du rajout."""
    with schema_context("demo"):
        initialiser_roles_par_defaut()
        role_cp = Role.objects.get(code="CP", supprime_le__isnull=True)

    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)
        perm_montants = CataloguePermission.objects.get(
            code="projets.voir_montants", supprime_le__isnull=True
        )
        codes_initiaux = list(
            mod_projets.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )
        if "projets.voir_montants" not in codes_initiaux:
            mod_projets.permissions.add(perm_montants)
            codes_initiaux.append("projets.voir_montants")

    with schema_context("demo"):
        rmp = RoleModulePermission.objects.filter(
            role=role_cp, module_catalogue=mod_projets
        ).first()
        if not rmp:
            rmp = RoleModulePermission.objects.filter(role=role_cp, module__code="projets").first()
        assert rmp is not None
        rmp.permissions_catalogue.add(perm_montants)
        assert rmp.permissions_catalogue.filter(code="projets.voir_montants").exists()

    codes_sans_montants = [c for c in codes_initiaux if c != "projets.voir_montants"]

    # 1. Retrait de projets.voir_montants du module
    rep_retrait = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/permissions/",
        {"permissions": codes_sans_montants},
        format="json",
    )
    assert rep_retrait.status_code == status.HTTP_200_OK, rep_retrait.content

    with schema_context("demo"):
        rmp.refresh_from_db()
        assert not rmp.permissions_catalogue.filter(code="projets.voir_montants").exists()

    # 2. Remise de projets.voir_montants au module -> Le CP ne le récupère pas (A-05)
    rep_remise = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/permissions/",
        {"permissions": codes_initiaux},
        format="json",
    )
    assert rep_remise.status_code == status.HTTP_200_OK, rep_remise.content

    with schema_context("demo"):
        rmp.refresh_from_db()
        assert not rmp.permissions_catalogue.filter(code="projets.voir_montants").exists()


def test_affecter_modules_a_une_permission_du_catalogue(superviseur_client):
    """POST /admins/permissions/{id}/modules/ -> succès pour bon module, 400 (D2) pour mauvais."""
    with schema_context(get_public_schema_name()):
        perm_montants = CataloguePermission.objects.get(
            code="projets.voir_montants", supprime_le__isnull=True
        )

    rep_ok = superviseur_client.post(
        f"/api/v1/admins/permissions/{perm_montants.id}/modules/",
        {"modules": ["projets"]},
        format="json",
    )
    assert rep_ok.status_code == status.HTTP_200_OK, rep_ok.content
    assert "projets" in rep_ok.json()["modules_codes"]

    rep_ko = superviseur_client.post(
        f"/api/v1/admins/permissions/{perm_montants.id}/modules/",
        {"modules": ["chantier"]},
        format="json",
    )
    assert rep_ko.status_code == status.HTTP_400_BAD_REQUEST, rep_ko.content
    assert (
        "La permission « projets.voir_montants » appartient au module « projets » : "
        "elle ne peut pas être rattachée au module « chantier »."
        in str(rep_ko.json())
    )


def test_supprimer_une_permission_du_catalogue(schema_demo, superviseur_client):
    """DELETE /admins/permissions/{id}/ -> 200 ; la permission disparaît de GET modules et demo."""
    with schema_context("demo"):
        initialiser_roles_par_defaut()
        role_cp = Role.objects.get(code="CP", supprime_le__isnull=True)

    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.get(
            code="projets.voir_montants", supprime_le__isnull=True
        )
        perm_id = perm.id
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)
        mod_projets.permissions.add(perm)

    with schema_context("demo"):
        rmp = RoleModulePermission.objects.filter(
            role=role_cp, module_catalogue=mod_projets
        ).first()
        if not rmp:
            rmp = RoleModulePermission.objects.filter(role=role_cp, module__code="projets").first()
        if rmp:
            rmp.permissions_catalogue.add(perm)

    # Suppression
    rep_del = superviseur_client.delete(f"/api/v1/admins/permissions/{perm_id}/")
    assert rep_del.status_code == status.HTTP_200_OK, rep_del.content

    # Vérification dans GET /admins/modules/
    rep_modules = superviseur_client.get("/api/v1/admins/modules/")
    assert rep_modules.status_code == status.HTTP_200_OK
    for m in rep_modules.json():
        assert "projets.voir_montants" not in m["permissions_codes"]
        for p in m["permissions"]:
            assert p["id"] != str(perm_id)

    # Vérification dans demo
    with schema_context("demo"):
        assert not RoleModulePermission.objects.filter(permissions_catalogue__id=perm_id).exists()


def test_retablir_une_permission_du_registre(superviseur_client):
    """Supprimer puis recréer une permission du REGISTRE -> 201 avec même ID et rattachée."""
    with schema_context(get_public_schema_name()):
        perm = CataloguePermission.objects.get(code="projets.voir_montants")
        perm_id = perm.id

    # Supprimer si pas déjà supprimée
    superviseur_client.delete(f"/api/v1/admins/permissions/{perm_id}/")

    with schema_context(get_public_schema_name()):
        perm.refresh_from_db()
        assert perm.supprime_le is not None

    rep_create = superviseur_client.post(
        "/api/v1/admins/permissions/",
        {
            "code": "projets.voir_montants",
            "libelle": "Voir les montants financiers",
            "description": "Permet de voir les budgets et montants",
        },
        format="json",
    )
    assert rep_create.status_code == status.HTTP_201_CREATED, rep_create.content
    data = rep_create.json()
    assert data["code"] == "projets.voir_montants"
    assert str(data["id"]) == str(perm_id)
    assert "projets" in data["modules_codes"]


def test_acces_par_defaut_sans_effet(superviseur_client):
    """PATCH /admins/modules/{projets}/ {"acces_par_defaut": ...} -> inchangé (garde bf3ae8d)."""
    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets", supprime_le__isnull=True)
        codes_avant = set(
            mod_projets.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )

    rep = superviseur_client.patch(
        f"/api/v1/admins/modules/{mod_projets.id}/",
        {"acces_par_defaut": ["lecture"]},
        format="json",
    )
    assert rep.status_code == status.HTTP_200_OK, rep.content

    with schema_context(get_public_schema_name()):
        mod_projets.refresh_from_db()
        codes_apres = set(
            mod_projets.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )
        assert codes_apres == codes_avant
