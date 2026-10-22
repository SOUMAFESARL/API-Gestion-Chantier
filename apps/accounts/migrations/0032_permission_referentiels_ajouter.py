"""Migration de données : `projets.referentiels_ajouter` aux rôles DG, AD, DO et CP existants.

La permission est attribuable (non réservée à l'administration) : les autres rôles la reçoivent
par la matrice. S'exécute sur chaque tenant ; le catalogue (schéma public) la reçoit ici si
la synchronisation du registre n'a pas encore tourné — elle la retrouve ensuite par son code.
"""

from django.db import migrations

CODE = "projets.referentiels_ajouter"
LIBELLE = "Ajouter des types, groupes et listes de l'entreprise"
ROLES_PAR_DEFAUT = ("DG", "AD", "DO", "CP")


def ajouter_permission(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name == "public":
        return

    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")

    module = CatalogueModule.objects.filter(code="projets", supprime_le__isnull=True).first()
    permission = CataloguePermission.objects.filter(code=CODE, supprime_le__isnull=True).first()
    if permission is None:
        if module is None:
            return
        permission = CataloguePermission.objects.create(
            code=CODE, libelle=LIBELLE, description=LIBELLE, ordre=2, est_actif=True
        )
        permission.modules.set([module])

    for role in Role.objects.filter(code__in=ROLES_PAR_DEFAUT, supprime_le__isnull=True):
        for rmp in RoleModulePermission.objects.filter(role=role, supprime_le__isnull=True):
            code_module = None
            if rmp.module_catalogue_id:
                code_module = rmp.module_catalogue.code
            elif rmp.module_id:
                code_module = rmp.module.code
            if code_module and code_module.lower() == "projets":
                rmp.permissions_catalogue.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0031_reparer_prenom_double"),
        ("catalogue", "0011_peupler_referentiels"),
    ]

    operations = [migrations.RunPython(ajouter_permission, migrations.RunPython.noop)]
