"""Tests d'intégration validant l'alignement strict des APIs platform_admin avec le Frontend Next.js."""

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Module, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

HOTE_PLATEFORME = "localhost"


@pytest.fixture
def superuser_admin(db):
    """Crée un Super Admin dans le schéma public."""
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email="super.frontend@ccd-digital.ci").delete()
        return Utilisateur.objects.create_superuser(
            email="super.frontend@ccd-digital.ci",
            password="SuperPassword123!",
            nom="Admin",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )


@pytest.fixture
def client_admin(superuser_admin):
    client = APIClient()
    client.force_authenticate(user=superuser_admin)
    return client


@pytest.mark.django_db
class TestAlignementFrontendModules:
    """Valide les contrats de données attendus par `features/administration/adaptateur.ts`."""

    def test_modules_champs_frontend(self, client_admin):
        """Vérifie la présence de statut ('ACTIF'/'INACTIF') et acces_par_defaut."""
        rep = client_admin.get("/api/v1/admins/modules/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep.status_code == status.HTTP_200_OK
        data = rep.json()
        assert len(data) > 0
        for item in data:
            assert "statut" in item
            assert item["statut"] in ["ACTIF", "INACTIF"]
            assert "acces_par_defaut" in item
            assert isinstance(item["acces_par_defaut"], list)
            assert "est_actif" in item
            assert "permissions_codes" in item

    def test_creer_module_sans_code_avec_acces_par_defaut(self, client_admin):
        """Le frontend crée un module avec libelle, description et acces_par_defaut sans spécifier de code."""
        payload = {
            "libelle": "Parc Matériel & Grues",
            "description": "Suivi des engins de levage",
            "acces_par_defaut": ["lecture", "saisie"],
        }
        rep = client_admin.post("/api/v1/admins/modules/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
        assert rep.status_code == status.HTTP_201_CREATED
        data = rep.json()
        assert data["code"] == "parc_materiel_grues"
        assert data["libelle"] == "Parc Matériel & Grues"
        assert data["statut"] == "ACTIF"
        assert "lecture" in data["acces_par_defaut"]
        assert "saisie" in data["acces_par_defaut"]
        assert "LECTURE" in data["permissions_codes"]
        assert "ECRITURE" in data["permissions_codes"]

    def test_desactiver_et_reactiver_module(self, client_admin):
        """Vérifie POST /admins/modules/{id}/desactiver/ et /reactiver/ avec gestion du 409 Conflit."""
        rep = client_admin.get("/api/v1/admins/modules/", HTTP_HOST=HOTE_PLATEFORME)
        mod_id = rep.json()[0]["id"]

        # 1. Désactiver
        rep_desact = client_admin.post(f"/api/v1/admins/modules/{mod_id}/desactiver/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_desact.status_code == status.HTTP_200_OK
        assert rep_desact.json()["statut"] == "INACTIF"
        assert rep_desact.json()["est_actif"] is False

        # 2. Conflit si déjà désactivé (409)
        rep_conflit1 = client_admin.post(f"/api/v1/admins/modules/{mod_id}/desactiver/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_conflit1.status_code == status.HTTP_409_CONFLICT
        assert rep_conflit1.json()["erreur"]["code"] == "conflit"

        # 3. Réactiver
        rep_react = client_admin.post(f"/api/v1/admins/modules/{mod_id}/reactiver/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_react.status_code == status.HTTP_200_OK
        assert rep_react.json()["statut"] == "ACTIF"
        assert rep_react.json()["est_actif"] is True

        # 4. Conflit si déjà actif (409)
        rep_conflit2 = client_admin.post(f"/api/v1/admins/modules/{mod_id}/reactiver/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_conflit2.status_code == status.HTTP_409_CONFLICT
        assert rep_conflit2.json()["erreur"]["code"] == "conflit"


@pytest.mark.django_db
class TestAlignementFrontendComptesEtProfil:
    """Valide les endpoints d'administration d'équipe et de profil connecté."""

    def test_comptes_administrateurs_crud(self, client_admin, superuser_admin):
        """Vérifie GET /admins/comptes/, création, suspension et réactivation."""
        # 1. Lister
        rep = client_admin.get("/api/v1/admins/comptes/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep.status_code == status.HTTP_200_OK
        comptes = rep.json()
        assert len(comptes) >= 1
        super_compte = next(c for c in comptes if c["email"] == superuser_admin.email)
        assert super_compte["role"] == "SUPERVISEUR"
        assert super_compte["statut"] == "ACTIF"
        assert super_compte["nom_complet"] != ""

        # 2. Créer un nouvel agent
        payload = {
            "prenom": "Agent",
            "nom": "Support",
            "email": "agent.support@ccd-digital.ci",
            "role": "SUPPORT",
        }
        rep_creer = client_admin.post("/api/v1/admins/comptes/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_creer.status_code == status.HTTP_201_CREATED
        agent = rep_creer.json()
        assert agent["email"] == "agent.support@ccd-digital.ci"
        assert agent["role"] == "SUPPORT"
        assert agent["statut"] == "ACTIF"
        agent_id = agent["id"]

        # 3. Suspendre son propre compte -> Refusé 400
        rep_auto = client_admin.post(f"/api/v1/admins/comptes/{superuser_admin.id}/suspendre/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_auto.status_code == status.HTTP_400_BAD_REQUEST

        # 4. Suspendre l'agent -> 200 OK
        rep_susp = client_admin.post(f"/api/v1/admins/comptes/{agent_id}/suspendre/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_susp.status_code == status.HTTP_200_OK
        assert rep_susp.json()["statut"] == "SUSPENDU"

        # 5. Réactiver l'agent -> 200 OK
        rep_react = client_admin.post(f"/api/v1/admins/comptes/{agent_id}/reactiver/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_react.status_code == status.HTTP_200_OK
        assert rep_react.json()["statut"] == "ACTIF"

    def test_profil_moi_et_mot_de_passe(self, client_admin, superuser_admin):
        """Vérifie GET /admins/moi/, PATCH /admins/moi/ et POST /admins/moi/mot-de-passe/."""
        # 1. Profil
        rep = client_admin.get("/api/v1/admins/moi/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep.status_code == status.HTTP_200_OK
        moi = rep.json()
        assert moi["email"] == superuser_admin.email
        assert moi["role_global"] == "AD"
        assert moi["is_superuser"] is True
        assert moi["schema"] == "public"

        # 2. Modifier coordonnées
        payload = {"telephone": "+2250700000000", "prenom": "SuperHero"}
        rep_patch = client_admin.patch("/api/v1/admins/moi/", payload, format="json", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_patch.status_code == status.HTTP_200_OK
        assert rep_patch.json()["telephone"] == "+2250700000000"
        assert rep_patch.json()["prenom"] == "SuperHero"

        # 3. Changer mot de passe - Ancien faux -> 400
        rep_faux = client_admin.post(
            "/api/v1/admins/moi/mot-de-passe/",
            {"ancien_mot_de_passe": "FauxMdp123!", "nouveau_mot_de_passe": "NouveauSuper2026!"},
            format="json",
            HTTP_HOST=HOTE_PLATEFORME,
        )
        assert rep_faux.status_code == status.HTTP_400_BAD_REQUEST

        # 4. Changer mot de passe - Succès -> 200
        rep_ok = client_admin.post(
            "/api/v1/admins/moi/mot-de-passe/",
            {"ancien_mot_de_passe": "SuperPassword123!", "nouveau_mot_de_passe": "NouveauSuper2026!"},
            format="json",
            HTTP_HOST=HOTE_PLATEFORME,
        )
        assert rep_ok.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestRoutesAliasFrontend:
    """Vérifie que les routes sans préfixe '/admins/' appelées par apiAdministration répondent bien."""

    def test_routes_indicateurs_alias(self, client_admin):
        rep = client_admin.get("/api/v1/indicateurs/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep.status_code == status.HTTP_200_OK

        rep_t = client_admin.get("/api/v1/indicateurs/tendances/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_t.status_code == status.HTTP_200_OK

        rep_e = client_admin.get("/api/v1/indicateurs/evolution/", HTTP_HOST=HOTE_PLATEFORME)
        assert rep_e.status_code == status.HTTP_200_OK
