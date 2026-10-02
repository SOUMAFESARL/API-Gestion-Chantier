import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projets", "0019_merge_lots_budget_statuts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name="activite",
            name="date_debut_prevue",
            field=models.DateField(blank=True, null=True, verbose_name="date de début prévue"),
        ),
        migrations.AlterField(
            model_name="activite",
            name="date_fin_prevue",
            field=models.DateField(blank=True, null=True, verbose_name="date de fin prévue"),
        ),
        migrations.AddField(
            model_name="activite",
            name="budget_initial_montant",
            field=models.BigIntegerField(
                blank=True, null=True, verbose_name="budget initial (centimes FCFA)"
            ),
        ),
        migrations.AddField(
            model_name="activite",
            name="dependance",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="successeurs",
                to="projets.activite",
                verbose_name="commence après",
            ),
        ),
        migrations.AddField(
            model_name="activite",
            name="equipe",
            field=models.ManyToManyField(
                blank=True,
                related_name="activites_affectees",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
