# Generated for converting RoleModulePermission.module CharField to ForeignKey(Module)

import django.db.models.deletion
from django.db import migrations, models


def migrer_vers_fk(apps, schema_editor):
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    Module = apps.get_model("accounts", "Module")
    modules_map = {m.code: m for m in Module.objects.all()}

    for perm in RoleModulePermission.objects.all():
        mod = modules_map.get(perm.module)
        if mod:
            perm.module_fk = mod
            perm.save(update_fields=["module_fk"])
        else:
            # Sécurité : tout module orphelin restant est nettoyé
            perm.delete()


def migrer_vers_charfield(apps, schema_editor):
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    for perm in RoleModulePermission.objects.all():
        if perm.module_fk_id:
            Module = apps.get_model("accounts", "Module")
            mod = Module.objects.filter(id=perm.module_fk_id).first()
            if mod:
                perm.module = mod.code
                perm.save(update_fields=["module"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_create_module_and_seed"),
    ]

    operations = [
        # 1. Ajouter le champ temporaire nullable module_fk
        migrations.AddField(
            model_name="rolemodulepermission",
            name="module_fk",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="permissions_roles",
                to="accounts.module",
                verbose_name="module",
            ),
        ),
        # 2. Migrer les données en associant la FK au bon Module
        migrations.RunPython(
            migrer_vers_fk,
            reverse_code=migrer_vers_charfield,
        ),
        # 3. Supprimer l'ancienne contrainte d'unicité qui référençait le CharField
        migrations.RemoveConstraint(
            model_name="rolemodulepermission",
            name="uq_role_module_actif",
        ),
        # 4. Supprimer l'ancien champ CharField module
        migrations.RemoveField(
            model_name="rolemodulepermission",
            name="module",
        ),
        # 5. Renommer module_fk en module
        migrations.RenameField(
            model_name="rolemodulepermission",
            old_name="module_fk",
            new_name="module",
        ),
        # 6. Rendre le champ non-nul (null=False)
        migrations.AlterField(
            model_name="rolemodulepermission",
            name="module",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="permissions_roles",
                to="accounts.module",
                verbose_name="module",
            ),
        ),
        # 7. Ré-appliquer la contrainte d'unicité sur (role, module)
        migrations.AddConstraint(
            model_name="rolemodulepermission",
            constraint=models.UniqueConstraint(
                condition=models.Q(supprime_le__isnull=True),
                fields=("role", "module"),
                name="uq_role_module_actif",
            ),
        ),
    ]
