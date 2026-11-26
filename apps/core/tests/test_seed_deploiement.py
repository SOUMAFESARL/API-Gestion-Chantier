"""Tests unitaires du seed plateforme idempotent au déploiement (sans base de données)."""

from __future__ import annotations

import hashlib
import json
from io import StringIO
from unittest.mock import patch

from django.test import RequestFactory

from apps.core.services.initialisation import ensemencer_base_plateforme
from config.urls import migrer_bd_vue


class TestSeedDeploiement:
    def test_base_vide_peuple_catalogue_plans_feries_et_super_admin(self):
        out = StringIO()
        err = StringIO()
        with (
            patch("apps.catalogue.models.ModeleRole._base_manager.exists", return_value=False),
            patch("apps.entreprises.models.Entreprise.objects.exists", return_value=False),
            patch("apps.billing.models.Plan.objects.filter") as mock_plan_filter,
            patch("apps.accounts.models.Utilisateur.objects.filter") as mock_user_filter,
            patch("apps.core.services.initialisation.call_command") as mock_cmd,
        ):
            mock_plan_filter.return_value.exists.return_value = False
            mock_user_filter.return_value.exists.return_value = False

            ensemencer_base_plateforme(
                out,
                stderr=err,
                super_admin_email="Support@CCD-Digital.ci",
                super_admin_mot_de_passe="MotDePasseRobuste2026@",
            )

        appels = [c.args[0] for c in mock_cmd.call_args_list]
        assert appels == [
            "ensemencer_plateforme",
            "peupler_plans",
            "charger_jours_feries",
            "synchroniser_catalogue_permissions",
            "propager_roles_systeme",
            "creer_super_admin",
        ]
        dernier = mock_cmd.call_args_list[-1]
        assert dernier.kwargs["email"] == "support@ccd-digital.ci"
        assert dernier.kwargs["motdepasse"] == "MotDePasseRobuste2026@"

    def test_base_existante_necrase_ni_catalogue_ni_plans_ni_super_admin(self):
        out = StringIO()
        with (
            patch("apps.catalogue.models.ModeleRole._base_manager.exists", return_value=True),
            patch("apps.entreprises.models.Entreprise.objects.exists", return_value=True),
            patch(
                "apps.catalogue.models.ModeleDecoupagePlateforme._base_manager.exists",
                return_value=True,
            ),
            patch(
                "apps.catalogue.models.ListeValeursPlateforme._base_manager.exists",
                return_value=True,
            ),
            patch("apps.billing.models.Plan.objects.filter") as mock_plan_filter,
            patch("apps.accounts.models.Utilisateur.objects.filter") as mock_user_filter,
            patch("apps.core.services.initialisation.call_command") as mock_cmd,
        ):
            mock_plan_filter.return_value.exists.return_value = True
            mock_user_filter.return_value.exists.return_value = True

            ensemencer_base_plateforme(
                out,
                super_admin_email="support@ccd-digital.ci",
                super_admin_mot_de_passe="MotDePasseRobuste2026@",
            )

        appels = [c.args[0] for c in mock_cmd.call_args_list]
        assert appels == [
            "charger_jours_feries",
            "synchroniser_catalogue_permissions",
            "propager_roles_systeme",
        ]
        assert "ensemencer_plateforme" not in appels
        assert "peupler_plans" not in appels
        assert "creer_super_admin" not in appels
        assert "Super Admin déjà présent" in out.getvalue()

    def test_base_avec_entreprises_et_decoupage_manquant_synchronise_sans_detruire(self):
        out = StringIO()
        with (
            patch("apps.catalogue.models.ModeleRole._base_manager.exists", return_value=True),
            patch("apps.entreprises.models.Entreprise.objects.exists", return_value=True),
            patch(
                "apps.catalogue.models.ModeleDecoupagePlateforme._base_manager.exists",
                return_value=False,
            ),
            patch(
                "apps.catalogue.models.ListeValeursPlateforme._base_manager.exists",
                return_value=True,
            ),
            patch("apps.billing.models.Plan.objects.filter") as mock_plan_filter,
            patch("apps.accounts.models.Utilisateur.objects.filter") as mock_user_filter,
            patch("apps.core.services.initialisation.call_command") as mock_cmd,
        ):
            mock_plan_filter.return_value.exists.return_value = True
            mock_user_filter.return_value.exists.return_value = True

            ensemencer_base_plateforme(out)

        appels = [c.args[0] for c in mock_cmd.call_args_list]
        assert appels[0] == "synchroniser_catalogue_decoupage"
        assert "ensemencer_plateforme" not in appels

    def test_vue_migrer_bd_accepte_payload_json_et_appelle_seed(self, settings):
        jeton = "jeton-maintenance-test"
        settings.MAINTENANCE_TOKEN_SHA256 = hashlib.sha256(jeton.encode("utf-8")).hexdigest()

        requete = RequestFactory().post(
            "/api/v1/maintenance/migrer-bd/",
            data=json.dumps(
                {
                    "super_admin_email": "support@ccd-digital.ci",
                    "super_admin_mot_de_passe": "MotDePasseRobuste2026@",
                }
            ),
            content_type="application/json",
            HTTP_X_MAINTENANCE_TOKEN=jeton,
        )

        with (
            patch("config.urls._activer_role_proprietaire", return_value=False),
            patch("config.urls.call_command") as mock_cmd,
            patch("apps.core.services.initialisation.ensemencer_base_plateforme") as mock_seed,
            patch("config.urls.cache.clear") as mock_cache_clear,
        ):
            reponse = migrer_bd_vue(requete)

        assert reponse.status_code == 200
        corps = json.loads(reponse.content.decode("utf-8"))
        assert corps["statut"] == "succes"
        assert [c.args[0] for c in mock_cmd.call_args_list] == ["migrate", "verifier_isolation"]
        mock_seed.assert_called_once()
        assert mock_seed.call_args.kwargs["super_admin_email"] == "support@ccd-digital.ci"
        assert mock_seed.call_args.kwargs["super_admin_mot_de_passe"] == "MotDePasseRobuste2026@"
        mock_cache_clear.assert_called_once()

    def test_vue_migrer_bd_accepte_corps_vide_et_refuse_mauvais_jeton(self, settings):
        jeton = "jeton-maintenance-test"
        settings.MAINTENANCE_TOKEN_SHA256 = hashlib.sha256(jeton.encode("utf-8")).hexdigest()

        req_refusee = RequestFactory().post(
            "/api/v1/maintenance/migrer-bd/",
            HTTP_X_MAINTENANCE_TOKEN="faux",
        )
        assert migrer_bd_vue(req_refusee).status_code == 403

        req_vide = RequestFactory().post(
            "/api/v1/maintenance/migrer-bd/",
            HTTP_X_MAINTENANCE_TOKEN=jeton,
        )
        with (
            patch("config.urls._activer_role_proprietaire", return_value=False),
            patch("config.urls.call_command"),
            patch("apps.core.services.initialisation.ensemencer_base_plateforme") as mock_seed,
            patch("config.urls.cache.clear"),
        ):
            reponse = migrer_bd_vue(req_vide)

        assert reponse.status_code == 200
        assert mock_seed.call_args.kwargs["super_admin_email"] is None
        assert mock_seed.call_args.kwargs["super_admin_mot_de_passe"] is None
