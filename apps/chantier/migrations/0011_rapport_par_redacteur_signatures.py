"""Un rapport par rédacteur et par jour ; signataires attendus et signatures (30/10/2026)."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chantier", "0010_rattacher_element"),
        ("projets", "0046_unicite_role_reglable"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="rapportjournalier",
            name="uq_rapport_projet_jour",
        ),
        migrations.AddField(
            model_name="journalchantier",
            name="perimetre_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="journalchantier",
            name="signataires_attendus",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="journalchantier",
            name="signatures",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddConstraint(
            model_name="rapportjournalier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("supprime_le__isnull", True)),
                fields=("projet", "auteur", "date_rapport"),
                name="uq_rapport_projet_auteur_jour",
            ),
        ),
    ]
