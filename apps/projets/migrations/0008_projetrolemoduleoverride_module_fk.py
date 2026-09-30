# Generated for converting ProjetRoleModuleOverride.module CharField to ForeignKey(accounts.Module)

import django.db.models.deletion
from django.db import migrations, models


def migrer_overrides_vers_fk(apps, schema_editor):
    ProjetRoleModuleOverride = apps.get_model("projets", "ProjetRoleModuleOverride")
    Module = apps.get_model("accounts", "Module")
    modules_map = {m.code: m for m in Module.objects.all()}

    for override in ProjetRoleModuleOverride.objects.all():
        mod = modules_map.get(override.module)
        if mod:
            override.module_fk = mod
            override.save(update_fields=["module_fk"])
        else:
            override.delete()


def migrer_overrides_vers_charfield(apps, schema_editor):
    ProjetRoleModuleOverride = apps.get_model("projets", "ProjetRoleModuleOverride")
    for override in ProjetRoleModuleOverride.objects.all():
        if override.module_fk_id:
            Module = apps.get_model("accounts", "Module")
            mod = Module.objects.filter(id=override.module_fk_id).first()
            if mod:
                override.module = mod.code
                override.save(update_fields=["module"])


class Migration(migrations.Migration):

    dependencies = [
        ("projets", "0007_alter_affectationprojet_role_projet_and_more"),
        ("accounts", "0014_rolemodulepermission_module_fk"),
    ]

    operations = [
        # 1. Ajouter le champ temporaire nullable module_fk
        migrations.AddField(
            model_name="projetrolemoduleoverride",
            name="module_fk",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="overrides_projets",
                to="accounts.module",
                verbose_name="module",
            ),
        ),
        # 2. Migrer les données
        migrations.RunPython(
            migrer_overrides_vers_fk,
            reverse_code=migrer_overrides_vers_charfield,
        ),
        # 3. Supprimer l'ancienne contrainte d'unicité
        migrations.RemoveConstraint(
            model_name="projetrolemoduleoverride",
            name="uq_projet_role_module_actif",
        ),
        # 4. Supprimer l'ancien champ CharField
        migrations.RemoveField(
            model_name="projetrolemoduleoverride",
            name="module",
        ),
        # 5. Renommer module_fk en module
        migrations.RenameField(
            model_name="projetrolemoduleoverride",
            old_name="module_fk",
            new_name="module",
        ),
        # 6. Rendre le champ non-nul
        migrations.AlterField(
            model_name="projetrolemoduleoverride",
            name="module",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="overrides_projets",
                to="accounts.module",
                verbose_name="module",
            ),
        ),
        # 7. Ré-appliquer la contrainte d'unicité sur (projet, role, module)
        migrations.AddConstraint(
            model_name="projetrolemoduleoverride",
            constraint=models.UniqueConstraint(
                condition=models.Q(supprime_le__isnull=True),
                fields=("projet", "role", "module"),
                name="uq_projet_role_module_actif",
            ),
        ),
    ]
