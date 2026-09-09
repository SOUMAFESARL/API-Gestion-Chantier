"""Tests pour la gestion dynamique des rôles et des habilitations par module (RBAC Hybride)."""

import pytest
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import (
    creer_role,
    initialiser_roles_par_defaut,
    modifier_role,
    supprimer_role,
)
from apps.core.enums import ModuleChoix, NiveauAcces, RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet
from apps.projets.services.overrides import (
    get_matrice_permissions_projet,
    set_override_permission_projet,
    supprimer_override_permission_projet,
)
from apps.tiers.models import Tiers

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def admin_user(db):
    with schema_context(SCHEMA):
        user, _ = Utilisateur.tous_objets.get_or_create(
            email="admin.roles@demo.ci",
            defaults={
                "nom": "Admin",
                "prenom": "Roles",
                "role_global": RoleGlobal.ADMIN,
                "statut": StatutUtilisateur.ACTIF,
                "is_owner": True,
            },
        )
        user.is_owner = True
        user.set_password("Password123!")
        user.save()
        yield user


@pytest.fixture
def client_api(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.mark.django_db
def test_initialiser_roles_par_defaut():
    with schema_context(SCHEMA):
        roles = initialiser_roles_par_defaut()
        assert len(roles) >= 13

        # Vérifie que l'admin a validation sur tous les modules
        role_ad = Role.objects.get(code=RoleGlobal.ADMIN)
        assert role_ad.est_systeme is True
        perms_ad = RoleModulePermission.objects.filter(role=role_ad)
        assert perms_ad.count() == len(ModuleChoix.values)
        for p in perms_ad:
            assert p.niveau == NiveauAcces.VALIDATION

        # Vérifie que tous les rôles ont accès complet à tous les modules à ce stade
        role_cc = Role.objects.get(code=RoleGlobal.CHEF_CHANTIER)
        perm_chantier = RoleModulePermission.objects.get(role=role_cc, module=ModuleChoix.CHANTIER)
        assert perm_chantier.niveau == NiveauAcces.VALIDATION
        perm_finance = RoleModulePermission.objects.get(role=role_cc, module=ModuleChoix.FINANCE)
        assert perm_finance.niveau == NiveauAcces.VALIDATION


@pytest.mark.django_db
def test_creer_et_modifier_role_personnalise(admin_user):
    with schema_context(SCHEMA):
        role = creer_role(
            code="MAGASINIER",
            libelle="Magasinier Principal",
            description="Gestionnaire des stocks et des réceptions",
            permissions_modules={
                ModuleChoix.STOCKS: NiveauAcces.ECRITURE,
                ModuleChoix.ACHATS: NiveauAcces.LECTURE,
            },
            cree_par=admin_user,
        )

        assert role.code == "MAGASINIER"
        assert role.est_systeme is False
        assert (
            RoleModulePermission.objects.get(role=role, module=ModuleChoix.STOCKS).niveau
            == NiveauAcces.ECRITURE
        )
        assert (
            RoleModulePermission.objects.get(role=role, module=ModuleChoix.ACHATS).niveau
            == NiveauAcces.LECTURE
        )
        assert (
            RoleModulePermission.objects.get(role=role, module=ModuleChoix.FINANCE).niveau
            == NiveauAcces.AUCUN
        )

        # Modification
        role_modifie = modifier_role(
            role=role,
            libelle="Magasinier Général",
            permissions_modules={
                ModuleChoix.STOCKS: NiveauAcces.VALIDATION,
            },
            modifie_par=admin_user,
        )
        assert role_modifie.libelle == "Magasinier Général"
        assert (
            RoleModulePermission.objects.get(role=role, module=ModuleChoix.STOCKS).niveau
            == NiveauAcces.VALIDATION
        )


@pytest.mark.django_db
def test_interdiction_supprimer_role_systeme():
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        role_ct = Role.objects.get(code=RoleGlobal.CONDUCTEUR_TRAVAUX)

        with pytest.raises(ValidationError) as exc:
            supprimer_role(role_ct)
        assert "Les rôles système ne peuvent pas être supprimés." in str(exc.value)


@pytest.mark.django_db
def test_supprimer_role_avec_reassignation_obligatoire(admin_user):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        role_source = creer_role(
            code="AIDE_COMPTABLE",
            libelle="Aide Comptable",
            permissions_modules={ModuleChoix.FINANCE: NiveauAcces.ECRITURE},
            cree_par=admin_user,
        )
        role_cible = Role.objects.get(code=RoleGlobal.VISITEUR)

        # Affecter un utilisateur à ce rôle
        collab, _ = Utilisateur.tous_objets.get_or_create(
            email="collab.test@demo.ci",
            defaults={"nom": "Test", "role_global": RoleGlobal.VISITEUR},
        )
        collab.role_personnalise = role_source
        collab.save()

        # 1. Tentative de suppression sans rôle de réassignation -> doit échouer
        with pytest.raises(ValidationError) as exc:
            supprimer_role(role_source)
        assert "Veuillez spécifier un rôle de remplacement" in str(exc.value)

        # 2. Suppression avec réassignation valide (Option B)
        res = supprimer_role(role_source, reassigner_vers_role=role_cible, supprime_par=admin_user)
        assert res["utilisateurs_reassignes"] == 1

        # Vérifie que le collaborateur a bien été réassigné
        collab.refresh_from_db()
        assert collab.role_personnalise == role_cible

        # Vérifie que l'ancien rôle est supprimé logiquement
        role_source.refresh_from_db()
        assert role_source.est_actif is False
        assert role_source.supprime_le is not None


@pytest.mark.django_db
def test_surcharge_permissions_par_projet(admin_user):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        client_tiers, _ = Tiers.objects.get_or_create(
            raison_sociale="Client Test",
            defaults={"telephone": "+22501020304"},
        )
        projet, _ = Projet.objects.get_or_create(
            reference="PRJ-2026-TEST",
            defaults={
                "nom": "Chantier Test Droits",
                "client": client_tiers,
                "ville": "Abidjan",
                "date_debut_prevue": "2026-09-01",
                "date_fin_prevue": "2026-12-31",
                "chef_projet": admin_user,
            },
        )

        role_cc = Role.objects.get(code=RoleGlobal.CHEF_CHANTIER)

        # Vérifie la matrice par défaut du projet (initialement VALIDATION)
        matrice = get_matrice_permissions_projet(projet)
        cc_info = next(r for r in matrice if r["code"] == RoleGlobal.CHEF_CHANTIER)
        assert cc_info["modules"][ModuleChoix.ACHATS]["niveau"] == NiveauAcces.VALIDATION
        assert cc_info["modules"][ModuleChoix.ACHATS]["est_surcharge"] is False

        # Appliquer une surcharge : restreindre la saisie des achats à LECTURE sur ce chantier
        set_override_permission_projet(
            projet=projet,
            role=role_cc,
            module=ModuleChoix.ACHATS,
            niveau=NiveauAcces.LECTURE,
            modifie_par=admin_user,
        )

        matrice_apres = get_matrice_permissions_projet(projet)
        cc_apres = next(r for r in matrice_apres if r["code"] == RoleGlobal.CHEF_CHANTIER)
        assert cc_apres["modules"][ModuleChoix.ACHATS]["niveau"] == NiveauAcces.LECTURE
        assert cc_apres["modules"][ModuleChoix.ACHATS]["est_surcharge"] is True

        # Réinitialiser vers le défaut
        supprimer_override_permission_projet(projet, role_cc, ModuleChoix.ACHATS)
        matrice_reinit = get_matrice_permissions_projet(projet)
        cc_reinit = next(r for r in matrice_reinit if r["code"] == RoleGlobal.CHEF_CHANTIER)
        assert cc_reinit["modules"][ModuleChoix.ACHATS]["niveau"] == NiveauAcces.VALIDATION
        assert cc_reinit["modules"][ModuleChoix.ACHATS]["est_surcharge"] is False


@pytest.mark.django_db
def test_api_roles_crud(client_api):
    with schema_context(SCHEMA):
        # 1. GET /api/v1/roles/
        rep = client_api.get("/api/v1/roles/", HTTP_HOST=HOTE)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()
        assert len(data) >= 7

        # 2. POST /api/v1/roles/ (Création)
        creation_data = {
            "code": "METREUR",
            "libelle": "Métreur Vérificateur",
            "description": "Calculs des métrés et validation des attachements",
            "permissions_modules": {
                ModuleChoix.PROJETS: NiveauAcces.LECTURE,
                ModuleChoix.CHANTIER: NiveauAcces.VALIDATION,
            },
        }
        rep_create = client_api.post("/api/v1/roles/", creation_data, format="json", HTTP_HOST=HOTE)
        assert rep_create.status_code == status.HTTP_201_CREATED
        role_id = rep_create.json()["id"]

        # 3. GET /api/v1/roles/{id}/
        rep_detail = client_api.get(f"/api/v1/roles/{role_id}/", HTTP_HOST=HOTE)
        assert rep_detail.status_code == status.HTTP_200_OK
        assert rep_detail.json()["libelle"] == "Métreur Vérificateur"

        # 4. PATCH /api/v1/roles/{id}/
        rep_patch = client_api.patch(
            f"/api/v1/roles/{role_id}/",
            {"libelle": "Métreur Senior"},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep_patch.status_code == status.HTTP_200_OK
        assert rep_patch.json()["libelle"] == "Métreur Senior"

        # 5. POST /api/v1/roles/{id}/supprimer/ (Sans substitution -> 400 substitution_obligatoire)
        rep_del_fail = client_api.post(
            f"/api/v1/roles/{role_id}/supprimer/",
            {},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep_del_fail.status_code == status.HTTP_400_BAD_REQUEST
        assert rep_del_fail.json()["erreur"]["code"] == "substitution_obligatoire"

        # 6. POST /api/v1/roles/{id}/supprimer/ (Avec substitution valide -> 200 OK)
        role_conducteur = Role.objects.get(code=RoleGlobal.CONDUCTEUR_TRAVAUX)
        rep_del = client_api.post(
            f"/api/v1/roles/{role_id}/supprimer/",
            {"role_substitution_id": str(role_conducteur.id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep_del.status_code == status.HTTP_200_OK
        assert rep_del.json()["role_supprime"] == "METREUR"
        assert rep_del.json()["utilisateurs_reassignes"] == 0
        assert rep_del.json()["affectations_reassignees"] == 0


@pytest.mark.django_db
def test_permission_module_enforcement():
    from rest_framework.response import Response
    from rest_framework.views import APIView

    from apps.core.permissions import PermissionModule

    class VueChantierEcriture(APIView):
        permission_classes = [PermissionModule.pour(ModuleChoix.CHANTIER, NiveauAcces.ECRITURE)]

        def post(self, request):
            return Response({"autorise": True})

    class VueFinanceValidation(APIView):
        permission_classes = [PermissionModule.pour(ModuleChoix.FINANCE, NiveauAcces.VALIDATION)]

        def post(self, request):
            return Response({"autorise": True})

    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()

        # Pour tester l'enforcement quand un niveau est insuffisant, on ajuste FINANCE à AUCUN pour CHEF_CHANTIER
        role_cc = Role.objects.get(code=RoleGlobal.CHEF_CHANTIER)
        RoleModulePermission.objects.filter(role=role_cc, module=ModuleChoix.FINANCE).update(
            niveau=NiveauAcces.AUCUN
        )

        # Chef de chantier : écriture sur Chantier (autorisé), pas sur Finance (refusé)
        cc_user, _ = Utilisateur.tous_objets.get_or_create(
            email="cc.test@demo.ci",
            defaults={
                "nom": "Kone",
                "role_global": RoleGlobal.CHEF_CHANTIER,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        client = APIClient()
        client.force_authenticate(user=cc_user)

        # 1. Chantier Ecriture -> Autorisé (200)
        req_chantier = client.post("/dummy-chantier/", HTTP_HOST=HOTE)
        vue_chantier = VueChantierEcriture.as_view()
        response_chantier = vue_chantier(req_chantier.wsgi_request)
        assert response_chantier.status_code == status.HTTP_200_OK

        # 2. Finance Validation -> Refusé (403)
        req_finance = client.post("/dummy-finance/", HTTP_HOST=HOTE)
        vue_finance = VueFinanceValidation.as_view()
        response_finance = vue_finance(req_finance.wsgi_request)
        assert response_finance.status_code == status.HTTP_403_FORBIDDEN
