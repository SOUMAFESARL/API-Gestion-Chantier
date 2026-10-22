import apps.projets.models.parametres_documents
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projets', '0040_mode_execution_referentiel'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ParametresDocuments',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('cree_le', models.DateTimeField(auto_now_add=True, verbose_name='créé le')),
                ('modifie_le', models.DateTimeField(auto_now=True, verbose_name='modifié le')),
                ('supprime_le', models.DateTimeField(blank=True, db_index=True, help_text='Non nul = ligne supprimée logiquement. Jamais de suppression physique.', null=True, verbose_name='supprimé le')),
                ('cle', models.CharField(default='unique', editable=False, max_length=10, verbose_name='clé')),
                ('entete_afficher_logo', models.BooleanField(default=True, verbose_name="afficher le logo dans l'en-tête")),
                ('entete_mentions', models.JSONField(default=apps.projets.models.parametres_documents.mentions_entete_par_defaut, help_text='Liste ordonnée de codes de mentions.', verbose_name="mentions de l'en-tête")),
                ('entete_texte_libre', models.CharField(blank=True, default='', max_length=200, verbose_name="texte libre de l'en-tête")),
                ('pied_mentions', models.JSONField(default=apps.projets.models.parametres_documents.mentions_pied_par_defaut, help_text='Liste ordonnée de codes de mentions.', verbose_name='mentions du pied de page')),
                ('pied_texte_libre', models.CharField(blank=True, default='', help_text='Par exemple le capital social ou des mentions légales.', max_length=300, verbose_name='texte libre du pied de page')),
                ('cree_par', models.ForeignKey(blank=True, help_text="Nul lorsque l'écriture vient du système.", null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='créé par')),
                ('supprime_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='supprimé par')),
            ],
            options={
                'verbose_name': 'paramètres des documents',
                'verbose_name_plural': 'paramètres des documents',
                'db_table': 'parametres_documents',
                'constraints': [models.UniqueConstraint(fields=('cle',), name='uq_parametres_documents_unique')],
            },
        ),
    ]
