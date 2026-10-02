# Generated manually for RapportJournalier constraints
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chantier", "0002_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="rapportjournalier",
            constraint=models.UniqueConstraint(
                condition=models.Q(lot__isnull=False),
                fields=("lot", "date_rapport"),
                name="uq_rapport_lot_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="rapportjournalier",
            constraint=models.UniqueConstraint(
                condition=models.Q(lot__isnull=True),
                fields=("projet", "date_rapport"),
                name="uq_rapport_projet_date",
            ),
        ),
    ]
