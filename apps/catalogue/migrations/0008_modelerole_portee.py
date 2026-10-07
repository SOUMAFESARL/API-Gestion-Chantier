from django.db import migrations, models


def initialiser_portee_modeles(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return
    ModeleRole = apps.get_model("catalogue", "ModeleRole")
    ModeleRole.objects.filter(code__in=["DG", "AD", "DO"]).update(portee="ENTREPRISE")
    ModeleRole.objects.exclude(code__in=["DG", "AD", "DO"]).update(portee="PROJET")


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0007_supprimer_verbes_generiques_catalogue"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelerole",
            name="portee",
            field=models.CharField(
                choices=[("ENTREPRISE", "Entreprise"), ("PROJET", "Projet")],
                default="PROJET",
                help_text="Portée par défaut : ENTREPRISE ou PROJET.",
                max_length=20,
                verbose_name="portée",
            ),
        ),
        migrations.RunPython(initialiser_portee_modeles, migrations.RunPython.noop),
    ]
