"""Migration de données : associe les permissions fondamentales à tous les modules actifs.

Garantit que la table Many-to-Many accounts_permission_modules est initialisée
dans tous les environnements (tests, staging, production) sans nécessiter de fallback.
"""

from django.db import migrations


def seed_permission_modules_m2m(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Module = apps.get_model("accounts", "Module")

    modules_actifs = list(Module.objects.filter(est_actif=True, supprime_le__isnull=True))
    if not modules_actifs:
        return

    for perm in Permission.objects.filter(est_actif=True, supprime_le__isnull=True):
        perm.modules.add(*modules_actifs)


def unseed_permission_modules_m2m(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_rendre_role_admin_supprimable_par_dg'),
    ]

    operations = [
        migrations.RunPython(seed_permission_modules_m2m, reverse_code=unseed_permission_modules_m2m),
    ]
