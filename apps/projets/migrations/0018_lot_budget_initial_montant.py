from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projets", "0017_alter_projet_statut")]
    operations = [
        migrations.AddField(
            model_name="lot",
            name="budget_initial_montant",
            field=models.BigIntegerField(
                blank=True, null=True, verbose_name="budget initial (centimes FCFA)"
            ),
        ),
    ]
