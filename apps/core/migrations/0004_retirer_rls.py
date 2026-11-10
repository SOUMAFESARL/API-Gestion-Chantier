"""Isolation Django seule : retrait des politiques, sans suppression de données.

Doit être exécutée par le propriétaire des tables. Les anciennes migrations
restent rejouables ; cette migration converge aussi depuis une base neuve.
"""

from importlib import import_module

from django.db import migrations

TABLES = import_module("apps.core.migrations.0001_isolation_rls").TABLES


def retirer(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        for politique in ("isolation_entreprise", "portee_plateforme_session"):
            schema_editor.execute(f'DROP POLICY IF EXISTS {politique} ON "{table}"')
    schema_editor.execute(
        """
CREATE OR REPLACE FUNCTION verifier_immuabilite_historique_date()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND OLD.entreprise_id::text = current_setting('ccd.purge_entreprise', true) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'RG-07 : historique_date est immuable. Operation % interdite.', TG_OP;
END;
$$ LANGUAGE plpgsql;
""",
        params=None,
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0003_sans_politique_plateforme")]
    operations = [migrations.RunPython(retirer)]
