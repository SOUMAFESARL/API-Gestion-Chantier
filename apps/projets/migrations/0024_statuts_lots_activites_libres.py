from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projets", "0023_repointer_override_vers_catalogue")]

    operations = [
        migrations.AlterField(
            model_name="lot",
            name="statut",
            field=models.TextField(default="PLANIFIE", verbose_name="statut"),
        ),
        migrations.AlterField(
            model_name="activite",
            name="statut",
            field=models.TextField(default="PLANIFIE", verbose_name="statut"),
        ),
    ]
