# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projets', '0035_calendrier_entreprise'),
    ]

    operations = [
        migrations.AlterField(
            model_name='projet',
            name='avancement_theorique',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text=(
                    "Déprécié : valeur de l'ancien moteur, plus lue ; "
                    "l'avancement temporel se calcule à chaque appel (SFD F3 RG-F3-04)."
                ),
                max_digits=5,
                verbose_name='avancement théorique (%)',
            ),
        ),
    ]
