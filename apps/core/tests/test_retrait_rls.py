"""Retrait de la RLS : diagnostic et graphe de migration sans base."""

from unittest.mock import MagicMock

from django.db.migrations.loader import MigrationLoader

from apps.core.rls import diagnostic_isolation


def test_role_plateforme_non_requis():
    connexion = MagicMock()
    curseur = connexion.cursor.return_value.__enter__.return_value
    curseur.__iter__.return_value = iter([])
    assert diagnostic_isolation(connexion) == []
    assert "pg_roles" not in curseur.execute.call_args.args[0]


def test_rls_residuelle_signalee():
    connexion = MagicMock()
    curseur = connexion.cursor.return_value.__enter__.return_value
    curseur.__iter__.return_value = iter([("utilisateur",)])
    assert len(diagnostic_isolation(connexion)) == 1


def test_migration_bloquee_remplacee_sans_reecrire_historique():
    loader = MigrationLoader(None)
    plan = loader.graph.forwards_plan(("core", "0004_retirer_rls"))
    assert ("core", "0003_plateforme_sans_role") not in plan
    assert ("core", "0003_sans_politique_plateforme") in plan


def test_moteur_sans_wrapper_rls(settings):
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
