"""Un rôle peut être « unique par projet » (décision du 30/10/2026).

C'est un réglage de l'entreprise : coché, une seule personne tient le rôle sur un projet. Les
rôles système chef de projet (CP) et chef de chantier (CC) le sont par défaut ; l'entreprise peut
décocher.
"""

from django.db import migrations, models

UNIQUES_PAR_DEFAUT = ("CP", "CC")


def cocher(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") == "public":
        return
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code__in=UNIQUES_PAR_DEFAUT, supprime_le__isnull=True).update(
        unique_par_projet=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0032_permission_referentiels_ajouter"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="unique_par_projet",
            field=models.BooleanField(
                default=False,
                help_text="Une seule personne à la fois tient ce rôle sur un projet.",
                verbose_name="unique par projet",
            ),
        ),
        migrations.RunPython(cocher, migrations.RunPython.noop),
    ]
