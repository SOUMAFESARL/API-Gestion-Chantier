"""La permission d'enregistrer les avenants au contrat (30/10/2026)."""

from django.db import migrations


def creer(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    Module = apps.get_model("catalogue", "CatalogueModule")
    Permission = apps.get_model("catalogue", "CataloguePermission")
    module = Module.objects.filter(code="projets", supprime_le__isnull=True).first()
    if module is None:
        return
    libelle = "Enregistrer et retirer les avenants au contrat"
    perm = Permission.objects.filter(
        code="projets.avenants_gerer", supprime_le__isnull=True
    ).first()
    if perm is None:
        perm = Permission.objects.create(
            code="projets.avenants_gerer",
            libelle=libelle,
            description=libelle,
            ordre=3,
            est_actif=True,
        )
    perm.modules.add(module)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0017_permissions_journal"),
    ]

    operations = [
        migrations.RunPython(creer, migrations.RunPython.noop),
    ]
