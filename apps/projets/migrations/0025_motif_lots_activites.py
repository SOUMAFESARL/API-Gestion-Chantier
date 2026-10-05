from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projets", "0024_statuts_lots_activites_libres")]

    operations = [
        migrations.AddField(
            model_name="lot",
            name="motif",
            field=models.TextField(blank=True, default="", verbose_name="motif"),
        ),
        migrations.AddField(
            model_name="activite",
            name="motif",
            field=models.TextField(blank=True, default="", verbose_name="motif"),
        ),
    ]
