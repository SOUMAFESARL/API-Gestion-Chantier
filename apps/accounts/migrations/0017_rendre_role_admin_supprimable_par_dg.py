# Migration 0017 — Rendre le rôle Administrateur (AD) supprimable par le DG
# Seul le Directeur Général (DG) reste un rôle système immuable.

from django.db import migrations


def rendre_admin_supprimable(apps, schema_editor):
    """Passe est_systeme=False sur le rôle Administrateur (AD) pour permettre sa suppression par le DG."""
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code="AD").update(est_systeme=False)


def annuler_suppression(apps, schema_editor):
    """Rollback : remet est_systeme=True sur le rôle Administrateur (AD)."""
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code="AD").update(est_systeme=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_permission_modules_m2m"),
    ]

    operations = [
        migrations.RunPython(
            rendre_admin_supprimable,
            reverse_code=annuler_suppression,
        ),
    ]
