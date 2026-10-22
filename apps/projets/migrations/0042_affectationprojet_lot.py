import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projets', '0041_parametres_documents'),
    ]

    operations = [
        migrations.AddField(
            model_name='affectationprojet',
            name='lot',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='affectations_chef_chantier',
                to='projets.lot',
                verbose_name='lot',
            ),
        ),
    ]
