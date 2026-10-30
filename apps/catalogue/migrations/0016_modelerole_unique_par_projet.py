"""Valeur de départ du réglage « unique par projet » des rôles système (30/10/2026)."""

from django.db import migrations, models

UNIQUES_PAR_DEFAUT = ("CP", "CC")


def cocher(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    ModeleRole = apps.get_model("catalogue", "ModeleRole")
    ModeleRole.objects.filter(code__in=UNIQUES_PAR_DEFAUT, supprime_le__isnull=True).update(
        unique_par_projet=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0015_permissions_decoupage"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelerole",
            name="unique_par_projet",
            field=models.BooleanField(
                default=False,
                help_text="Valeur de départ du réglage « unique par projet » des entreprises.",
                verbose_name="unique par projet",
            ),
        ),
        migrations.RunPython(cocher, migrations.RunPython.noop),
    ]
