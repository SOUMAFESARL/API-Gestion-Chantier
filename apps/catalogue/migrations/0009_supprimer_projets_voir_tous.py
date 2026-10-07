from django.db import migrations
from django.utils import timezone


def supprimer_projets_voir_tous(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")
    now = timezone.now()
    CataloguePermission.objects.filter(code="projets.voir_tous").update(
        supprime_le=now,
        est_actif=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0008_modelerole_portee"),
    ]

    operations = [
        migrations.RunPython(supprimer_projets_voir_tous, migrations.RunPython.noop),
    ]
