from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_admin', '0002_identite_plateforme'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParametresMessagerie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hote', models.CharField(blank=True, default='', max_length=255, verbose_name='serveur SMTP')),
                ('port', models.PositiveIntegerField(default=587, verbose_name='port')),
                ('chiffrement', models.CharField(choices=[('STARTTLS', 'STARTTLS (port 587)'), ('SSL', 'SSL/TLS (port 465)'), ('AUCUN', 'Aucun')], default='STARTTLS', max_length=10, verbose_name='chiffrement')),
                ('identifiant', models.CharField(blank=True, default='', max_length=254, verbose_name='identifiant')),
                ('mot_de_passe_chiffre', models.TextField(blank=True, default='', verbose_name='mot de passe chiffré')),
                ('expediteur', models.CharField(blank=True, default='', max_length=254, verbose_name='expéditeur')),
                ('modifie_le', models.DateTimeField(auto_now=True, verbose_name='modifié le')),
            ],
            options={
                'verbose_name': 'messagerie de la plateforme',
                'verbose_name_plural': 'messagerie de la plateforme',
                'db_table': 'parametres_messagerie',
            },
        ),
    ]
