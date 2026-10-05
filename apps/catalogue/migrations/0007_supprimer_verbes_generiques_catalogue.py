"""Migration de données : suppression des 4 verbes génériques du catalogue (A-03).

Règles : A-03.
Les 4 verbes génériques (LECTURE, ECRITURE, VALIDATION, SUPPRESSION) sortent du catalogue.
Marquage supprime_le (soft delete) et est_actif=False pour préserver l'intégrité référentielle multi-tenant.
"""

from django.db import migrations
from django.utils import timezone


def supprimer_verbes_generiques(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return

    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")
    verbes_interdits = ["LECTURE", "ECRITURE", "VALIDATION", "SUPPRESSION"]
    now = timezone.now()
    CataloguePermission.objects.filter(code__in=verbes_interdits).update(
        supprime_le=now,
        est_actif=False,
    )


def restaurer_verbes_generiques(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0006_supprimer_niveau_max_modele_role_module"),
    ]

    operations = [
        migrations.RunPython(supprimer_verbes_generiques, restaurer_verbes_generiques),
    ]
