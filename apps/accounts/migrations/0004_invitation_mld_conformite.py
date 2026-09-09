# Generated for MLD §5.2 compliance

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_jetonreinitialisation'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invitation',
            name='jeton',
        ),
        migrations.AddField(
            model_name='invitation',
            name='nom',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='nom'),
        ),
        migrations.AddField(
            model_name='invitation',
            name='empreinte',
            field=models.CharField(db_index=True, max_length=64, unique=True, verbose_name='empreinte'),
        ),
        migrations.AddField(
            model_name='invitation',
            name='emetteur',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='invitations_emises',
                to=settings.AUTH_USER_MODEL,
                verbose_name='émetteur',
            ),
        ),
        migrations.AddField(
            model_name='invitation',
            name='utilise_le',
            field=models.DateTimeField(blank=True, null=True, verbose_name='utilisé le'),
        ),
    ]
