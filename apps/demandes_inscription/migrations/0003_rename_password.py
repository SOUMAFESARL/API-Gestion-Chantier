from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('demandes_inscription', '0002_normaliser')]

    operations = [
        migrations.RenameField(
            model_name='demandeinscription',
            old_name='mot_de_passe_transitoire',
            new_name='password',
        ),
    ]
