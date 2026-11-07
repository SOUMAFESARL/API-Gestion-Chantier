"""Clés composites d'isolation du journal de chantier (D9, règle R-3).

`(projet_id, entreprise_id) → projet(id, entreprise_id)` : un rapport, un blocage, une relance ou
une synthèse ne peut pas rattacher le projet d'une autre entreprise. Voir `projets` 0002.
"""

from django.db import migrations

ENFANTS = ["blocage", "rapport_journalier", "relance_journal", "synthese_periodique"]


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


class Migration(migrations.Migration):
    dependencies = [
        ("chantier", "0001_initial"),
        ("projets", "0001_initial"),
    ]

    operations = [cle_composite(table) for table in ENFANTS]
