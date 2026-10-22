"""Tests des invariants des rôles et des autorisations granulaires dynamiques.

Vérifie :
1. Un rôle créé est obligatoirement lié à TOUS les modules actifs du catalogue.
2. Les permissions sont renvoyées sous forme de tableau dynamique structuré.
3. Les permissions sont non-hiérarchiques : un rôle avec chantier.valider seul ne peut pas effectuer chantier.rediger.
"""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.accounts.models import Module, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import (
    creer_role,
    initialiser_modules_par_defaut,
)
from apps.catalogue.models import CatalogueModule, CataloguePermission
from apps.core.droits import APermission
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.dyn@demo.ci",
            defaults={
                "nom": "Directeur",
                "prenom": "Admin",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": True,
            },
        )
        user.is_owner = True
        user.set_password("Password123!")
        user.save()
        return user


@pytest.fixture
def client_api(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.mark.django_db
def test_role_obligatoirement_lie_a_tous_les_modules():
    """Vérifie que la création d'un rôle le lie systématiquement à l'intégralité des modules actifs."""
    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()

        modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
        nb_modules = len(modules_actifs)
        assert nb_modules >= 5

        role = creer_role(
            code="AUDITEUR_EXTERNE",
            libelle="Auditeur Externe",
            permissions_modules={"projets": ["projets.lire"]},
        )

        rpm_qs = RoleModulePermission.objects.filter(role=role, supprime_le__isnull=True)
        assert rpm_qs.count() >= nb_modules

        rpm_projets = rpm_qs.get(module__code="projets")
        assert rpm_projets.permissions_catalogue.filter(code="projets.lire").exists()

        rpm_chantier = rpm_qs.get(module__code="chantier")
        assert rpm_chantier.permissions_catalogue.count() == 0


@pytest.mark.django_db
def test_tableau_dynamique_modules_et_permissions_api(client_api):
    """Vérifie que l'API renvoie les permissions sous forme de tableau dynamique complet."""
    with schema_context(SCHEMA):
        role = creer_role(
            code="RESPONSABLE_QSE",
            libelle="Responsable QSE",
            permissions_modules=[
                {"module": "chantier", "permissions": ["chantier.lire", "chantier.valider"]},
                {"module": "ged", "permissions": ["ged.lire"]},
            ],
        )

        rep = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()

        assert isinstance(data["modules"], list)
        assert len(data["modules"]) >= 5

        premier_module = data["modules"][0]
        assert "module_id" in premier_module
        assert "module_code" in premier_module
        assert "module_libelle" in premier_module
        assert "module_icone" in premier_module
        assert "module_ordre" in premier_module
        assert "permissions" in premier_module
        assert isinstance(premier_module["permissions"], list)

        mod_chantier = next(m for m in data["modules"] if m["module_code"] == "chantier")
        codes_chantier = [p["code"] for p in mod_chantier["permissions"]]
        assert "chantier.lire" in codes_chantier
        assert "chantier.valider" in codes_chantier
        assert "chantier.rediger" not in codes_chantier


@pytest.mark.django_db
def test_non_hierarchie_permissions_validation_seule():
    """Vérifie qu'un rôle ayant chantier.valider seul NE PEUT PAS faire chantier.rediger."""
    class VueActionEcriture(APIView):
        permission_classes = [APermission.pour("chantier.rediger")]

        def post(self, request):
            return Response({"action": "ecriture_reussie"})

    class VueActionValidation(APIView):
        permission_classes = [APermission.pour("chantier.valider")]

        def post(self, request):
            return Response({"action": "validation_reussie"})

    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()

        role_controleur = creer_role(
            code="CONTROLEUR",
            libelle="Contrôleur Technique",
            permissions_modules={"chantier": ["chantier.valider"]},
        )

        user_controleur, _ = Utilisateur.tous_objets.get_or_create(
            email="controleur@demo.ci",
            defaults={
                "nom": "Diallo",
                "role_personnalise": role_controleur,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user_controleur.role_personnalise = role_controleur
        user_controleur.save()

        client = APIClient()
        client.force_authenticate(user=user_controleur)

        req_val = client.post("/dummy-val/", HTTP_HOST=HOTE)
        vue_val = VueActionValidation.as_view()
        rep_val = vue_val(req_val.wsgi_request)
        assert rep_val.status_code == status.HTTP_200_OK

        req_ecr = client.post("/dummy-ecr/", HTTP_HOST=HOTE)
        vue_ecr = VueActionEcriture.as_view()
        rep_ecr = vue_ecr(req_ecr.wsgi_request)
        assert rep_ecr.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_permissions_modules_format_liste_codes_dynamique(client_api):
    """Vérifie que permissions_modules renvoie un dictionnaire de listes de codes de permissions."""
    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()

        role = creer_role(
            code="AUDITEUR_TEST",
            libelle="Auditeur Test",
            permissions_modules={
                "projets": ["projets.lire", "projets.changer_statut"],
                "tiers": ["tiers.lire"],
            },
        )

        rep = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()

        assert "permissions_modules" in data
        perms_modules = data["permissions_modules"]
        assert isinstance(perms_modules, dict)

        assert "projets.lire" in perms_modules["projets"]
        assert "projets.changer_statut" in perms_modules["projets"]
        assert "tiers.lire" in perms_modules["tiers"]

        # Le module GED n'expose plus de permission au catalogue : sa liste reste vide
        assert perms_modules["ged"] == []
        assert perms_modules["chantier"] == []
        assert perms_modules["pilotage"] == []


@pytest.mark.django_db
def test_dynamisme_ajout_et_modification_permission_en_base(client_api):
    """Vérifie que l'ajout ou la modification d'une permission en base remonte dynamiquement sans code en dur."""
    with schema_context(get_public_schema_name()):
        mod_projets = CatalogueModule.objects.get(code="projets")
        perm_export, _ = CataloguePermission.objects.update_or_create(
            code="projets.export_excel",
            defaults={
                "libelle": "Export Excel / PDF",
                "description": "Exportation des données comptables et métrés",
                "ordre": 10,
                "est_actif": True,
                "supprime_le": None,
            },
        )
        perm_export.modules.add(mod_projets)

    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()

        role = creer_role(
            code="COMPTABLE_EXPORT",
            libelle="Comptable Export",
            permissions_modules={"projets": ["projets.lire", "projets.export_excel"]},
        )

        rep = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()
        assert "projets.export_excel" in data["permissions_modules"]["projets"]
        assert "projets.lire" in data["permissions_modules"]["projets"]

    with schema_context(get_public_schema_name()):
        perm_export.code = "projets.export_donnees"
        perm_export.libelle = "Exportation des données"
        perm_export.save()

    with schema_context(SCHEMA):
        rep_apres = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep_apres.status_code == status.HTTP_200_OK
        data_apres = rep_apres.json()
        assert "projets.export_donnees" in data_apres["permissions_modules"]["projets"]
        assert "projets.export_excel" not in data_apres["permissions_modules"]["projets"]
