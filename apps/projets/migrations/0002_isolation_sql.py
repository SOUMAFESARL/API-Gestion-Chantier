"""Ce que Django n'exprime pas seul : clés composites d'isolation et immuabilité (D9).

- **Clés composites** `(projet_id, entreprise_id) → projet(id, entreprise_id)` sur les enfants
  directs du projet (règle R-3) : même avec un identifiant de projet correct, une ligne ne peut pas
  rattacher un projet d'une autre entreprise. Différées, comme les clés de Django.
- **Immuabilité de `historique_date`** (RG-07, RG-11) : mise à jour et suppression refusées, sauf
  la purge de l'entreprise de la ligne par la suppression définitive — la session a pris le rôle
  de la portée plateforme et `ccd.purge_entreprise` (local à la transaction, posé par
  `apps.tenants.services.suppression_definitive`) désigne l'entreprise de la ligne.

Reprend, depuis la remise à zéro des migrations (lot 6), les anciennes `projets` 0003 et 0004.
"""

from django.db import migrations

from apps.core.rls import role_plateforme

ENFANTS = [
    "alerte_retard",
    "arret_chantier",
    "avenant",
    "projet_contrat",
    "point_avancement",
    "niveau_projet",
    "element",
    "dependance_element",
    "equipe_chantier",
    "affectation_projet",
    "historique_date",
    "sante_projet_snapshot",
]


def cle_composite(table: str) -> migrations.RunSQL:
    nom = f"fk_{table}_projet_meme_entreprise"
    return migrations.RunSQL(
        sql=(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{nom}" '
            f'FOREIGN KEY ("projet_id", "entreprise_id") REFERENCES "projet" ("id", "entreprise_id") '
            f"DEFERRABLE INITIALLY DEFERRED;"
        ),
        reverse_sql=f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{nom}";',
    )


def _immuabilite() -> str:
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

DROP TRIGGER IF EXISTS trg_historique_date_immuable ON historique_date;
CREATE TRIGGER trg_historique_date_immuable
BEFORE UPDATE OR DELETE ON historique_date
FOR EACH ROW
EXECUTE FUNCTION verifier_immuabilite_historique_date();
"""


class Migration(migrations.Migration):
    dependencies = [("projets", "0001_initial")]

    operations = [
        *(cle_composite(table) for table in ENFANTS),
        migrations.RunSQL(
            sql=_immuabilite(),
            reverse_sql=(
                "DROP TRIGGER IF EXISTS trg_historique_date_immuable ON historique_date;"
                "DROP FUNCTION IF EXISTS verifier_immuabilite_historique_date();"
            ),
        ),
    ]
