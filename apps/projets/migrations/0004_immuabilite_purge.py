"""`historique_date` reste immuable — sauf pour la purge de son entreprise (D9, lot 5).

Sous le multi-schéma, la suppression définitive d'une entreprise passait par `DROP SCHEMA`, que le
déclencheur ne voyait pas. Elle supprime désormais par `entreprise_id`, ligne à ligne : le
déclencheur la refuserait.

Il ne la laisse passer qu'à deux conditions, toutes deux posées par
`apps.tenants.services.suppression_definitive` et locales à sa transaction :

- la session a pris le rôle de la portée plateforme ;
- le réglage `ccd.purge_entreprise` désigne **l'entreprise de la ligne**.

Une mise à jour reste toujours refusée, et une suppression ordinaire aussi.
"""

from django.db import migrations

from apps.core.rls import role_plateforme


def _fonction() -> str:
    return f"""
CREATE OR REPLACE FUNCTION verifier_immuabilite_historique_date()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_user = '{role_plateforme()}'
       AND OLD.entreprise_id::text = current_setting('ccd.purge_entreprise', true) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'RG-07 : La table historique_date est strictement immuable (append-only). Opération % interdite.', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


ANCIENNE = """
CREATE OR REPLACE FUNCTION verifier_immuabilite_historique_date()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'RG-07 : La table historique_date est strictement immuable (append-only). Opération % interdite.', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("projets", "0003_isolation_sql")]

    operations = [migrations.RunSQL(sql=_fonction(), reverse_sql=ANCIENNE)]
