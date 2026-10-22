"""Le mode d'exécution d'un lot n'est plus une énumération figée : il suit le référentiel."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projets", "0039_mise_a_jour_inline")]

    operations = [
        migrations.AlterField(
            model_name="lot",
            name="mode_execution",
            field=models.CharField(default="REGIE", max_length=60, verbose_name="mode d'exécution"),
        ),
        migrations.AlterField(
            model_name="referentielentreprise",
            name="categorie",
            field=models.CharField(
                choices=[
                    ("TYPE_PROJET", "Type de projet"),
                    ("LOT", "Nom de lot"),
                    ("MODE_EXECUTION", "Mode d'exécution"),
                ],
                max_length=20,
                verbose_name="catégorie",
            ),
        ),
    ]
