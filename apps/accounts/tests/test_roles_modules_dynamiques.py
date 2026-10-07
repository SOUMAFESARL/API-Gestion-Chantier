"""Tests des invariants des rôles et des autorisations granulaires dynamiques.

Vérifie :
1. Un rôle créé est obligatoirement lié à TOUS les modules actifs du catalogue.
2. Les permissions sont renvoyées sous forme de tableau dynamique structuré.
3. Le niveau supérieur d'une permission ne confère pas l'accès aux niveaux inférieurs (non-hiérarchique) :
   ex: un rôle avec VALIDATION seule ne peut pas effectuer une ECRITURE.
"""

import pytest
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.accounts.models import Module, Permission, Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import (
    creer_role,
    initialiser_modules_par_defaut,
    initialiser_permissions_par_defaut,
)
from apps.core.droits import APermission
from apps.core.enums import ModuleChoix, RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()
        initialiser_permissions_par_defaut()
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
        initialiser_permissions_par_defaut()

        modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
        nb_modules = len(modules_actifs)
        assert nb_modules >= 5

        # Création d'un rôle personnalisé en ne précisant que des permissions sur 'projets'
        role = creer_role(
            code="AUDITEUR_EXTERNE",
            libelle="Auditeur Externe",
            permissions_modules={"projets": ["LECTURE"]},
        )

        # Invariant de complétude : RoleModulePermission doit exister pour TOUS les modules
        rpm_qs = RoleModulePermission.objects.filter(role=role, supprime_le__isnull=True)
        assert rpm_qs.count() == nb_modules

        # Vérifier que 'projets' a LECTURE
        rpm_projets = rpm_qs.get(module__code="projets")
        assert rpm_projets.permissions.filter(code="LECTURE").exists()

        # Vérifier que les autres modules ('chantier', 'ged', etc.) sont liés avec permissions vides []
        rpm_chantier = rpm_qs.get(module__code="chantier")
        assert rpm_chantier.permissions.count() == 0


@pytest.mark.django_db
def test_tableau_dynamique_modules_et_permissions_api(client_api):
    """Vérifie que l'API renvoie les permissions sous forme de tableau dynamique complet."""
    with schema_context(SCHEMA):
        role = creer_role(
            code="RESPONSABLE_QSE",
            libelle="Responsable QSE",
            permissions_modules=[
                {"module": "chantier", "permissions": ["LECTURE", "VALIDATION"]},
                {"module": "ged", "permissions": ["LECTURE"]},
            ],
        )

        rep = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()

        # Le champ modules doit être une liste dynamique
        assert isinstance(data["modules"], list)
        assert len(data["modules"]) >= 5

        # Vérifier la structure de chaque élément du tableau
        premier_module = data["modules"][0]
        assert "module_id" in premier_module
        assert "module_code" in premier_module
        assert "module_libelle" in premier_module
        assert "module_icone" in premier_module
        assert "module_ordre" in premier_module
        assert "permissions" in premier_module
        assert isinstance(premier_module["permissions"], list)

        # Vérifier que 'chantier' porte les deux permissions attendues
        mod_chantier = next(m for m in data["modules"] if m["module_code"] == "chantier")
        codes_chantier = [p["code"] for p in mod_chantier["permissions"]]
        assert "LECTURE" in codes_chantier
        assert "VALIDATION" in codes_chantier
        assert "ECRITURE" not in codes_chantier


@pytest.mark.django_db
def test_non_hierarchie_permissions_validation_seule():
    """Vérifie qu'un rôle ayant VALIDATION seule NE PEUT PAS faire d'ECRITURE."""
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
        initialiser_permissions_par_defaut()

        # Rôle avec VALIDATION uniquement sur Chantier
        role_controleur = creer_role(
            code="CONTROLEUR",
            libelle="Contrôleur Technique",
            permissions_modules={"chantier": ["VALIDATION"]},
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

        # 1. Action Validation -> AUTORISÉ (200 OK) car il a VALIDATION
        req_val = client.post("/dummy-val/", HTTP_HOST=HOTE)
        vue_val = VueActionValidation.as_view()
        rep_val = vue_val(req_val.wsgi_request)
        assert rep_val.status_code == status.HTTP_200_OK

        # 2. Action Écriture -> REFUSÉ (403 Forbidden) car VALIDATION n'implique pas ECRITURE
        req_ecr = client.post("/dummy-ecr/", HTTP_HOST=HOTE)
        vue_ecr = VueActionEcriture.as_view()
        rep_ecr = vue_ecr(req_ecr.wsgi_request)
        assert rep_ecr.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_permissions_modules_format_liste_codes_dynamique(client_api):
    """Vérifie que permissions_modules renvoie un dictionnaire de listes de codes de permissions."""
    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()
        initialiser_permissions_par_defaut()

        role = creer_role(
            code="AUDITEUR_TEST",
            libelle="Auditeur Test",
            permissions_modules={
                "projets": ["LECTURE", "VALIDATION"],
                "ged": ["LECTURE"],
            },
        )

        rep = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()

        assert "permissions_modules" in data
        perms_modules = data["permissions_modules"]
        assert isinstance(perms_modules, dict)

        # Projets doit contenir exactement ['LECTURE', 'VALIDATION']
        assert "LECTURE" in perms_modules["projets"]
        assert "VALIDATION" in perms_modules["projets"]
        assert "lecture" in perms_modules["projets"]
        assert "validation" in perms_modules["projets"]

        # GED doit contenir ['LECTURE']
        assert "LECTURE" in perms_modules["ged"]
        assert "lecture" in perms_modules["ged"]

        # Les autres modules actifs doivent avoir une liste vide []
        assert perms_modules["chantier"] == []
        assert perms_modules["pilotage"] == []
        assert perms_modules["tiers"] == []


@pytest.mark.django_db
def test_dynamisme_ajout_et_modification_permission_en_base(client_api):
    """Vérifie que l'ajout ou la modification d'une permission en base remonte dynamiquement sans code en dur."""
    with schema_context(SCHEMA):
        initialiser_modules_par_defaut()
        initialiser_permissions_par_defaut()

        mod_projets = Module.objects.get(code="projets")

        # 1. Création dynamique d'une nouvelle permission en base de données
        perm_export, _ = Permission.objects.update_or_create(
            code="EXPORT_EXCEL",
            defaults={
                "libelle": "Export Excel / PDF",
                "description": "Exportation des données comptables et métrés",
                "ordre": 10,
                "est_actif": True,
            },
        )
        perm_export.modules.add(mod_projets)

        # Création d'un rôle portant cette nouvelle permission
        role = creer_role(
            code="COMPTABLE_EXPORT",
            libelle="Comptable Export",
            permissions_modules={"projets": ["LECTURE", "EXPORT_EXCEL"]},
        )

        # L'API doit renvoyer la nouvelle permission dynamiquement
        rep = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()
        assert "EXPORT_EXCEL" in data["permissions_modules"]["projets"]
        assert "LECTURE" in data["permissions_modules"]["projets"]
        assert "lecture" in data["permissions_modules"]["projets"]

        # 2. Modification dynamique du code de la permission en base (renommage)
        perm_export.code = "EXPORT_DONNEES"
        perm_export.libelle = "Exportation des données"
        perm_export.save()

        # Sans aucun redémarrage ni modification de code, l'API reflète immédiatement le nouveau code
        rep_apres = client_api.get(f"/api/v1/roles/{role.id}/", HTTP_HOST=HOTE)
        assert rep_apres.status_code == status.HTTP_200_OK
        data_apres = rep_apres.json()
        assert "EXPORT_DONNEES" in data_apres["permissions_modules"]["projets"]
        assert "EXPORT_EXCEL" not in data_apres["permissions_modules"]["projets"]
