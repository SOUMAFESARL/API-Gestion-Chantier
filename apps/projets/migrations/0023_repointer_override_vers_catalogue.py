"""Migration de données pour reparenter ProjetRoleModuleOverride vers catalogue_module et catalogue_permission."""

from django.db import migrations


def reparenter_overrides_vers_catalogue(apps, schema_editor):
    cursor = schema_editor.connection.cursor()

    # Vérifier si les tables locales nécessaires existent dans ce schéma
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'projet_role_module_override'
        );
    """)
    if not cursor.fetchone()[0]:
        return

    # 1. Reparentage de module_catalogue_id par matching sur le code
    cursor.execute("""
        UPDATE projet_role_module_override prmo
        SET module_catalogue_id = cm.id
        FROM module m, catalogue_module cm
        WHERE prmo.module_id = m.id
          AND m.code = cm.code
          AND prmo.module_catalogue_id IS NULL;
    """)

    # 2. Vérification d'intégrité : 0 orphelins non migrés
    cursor.execute("""
        SELECT COUNT(*)
        FROM projet_role_module_override
        WHERE module_id IS NOT NULL AND module_catalogue_id IS NULL;
    """)
    orphelins = cursor.fetchone()[0]
    if orphelins > 0:
        raise ValueError(
            f"ERREUR FATALE : {orphelins} ligne(s) de projet_role_module_override n'ont pas pu "
            f"être associées au catalogue partagé."
        )

    # 3. Migration de la table de liaison permissions -> permissions_catalogue
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'projet_role_module_override_permissions'
        );
    """)
    if cursor.fetchone()[0]:
        cursor.execute("""
            INSERT INTO projet_role_module_override_permissions_catalogue (
                projetrolemoduleoverride_id, cataloguepermission_id
            )
            SELECT pop.projetrolemoduleoverride_id, cp.id
            FROM projet_role_module_override_permissions pop
            JOIN permission p ON pop.permission_id = p.id
            JOIN catalogue_permission cp ON p.code = cp.code
            ON CONFLICT DO NOTHING;
        """)


def annuler_reparentage(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    cursor.execute("""
        UPDATE projet_role_module_override
        SET module_catalogue_id = NULL;
    """)
    cursor.execute("""
        DELETE FROM projet_role_module_override_permissions_catalogue;
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("projets", "0022_projetrolemoduleoverride_module_catalogue_and_more"),
        ("accounts", "0020_repointer_rolemodulepermission_vers_catalogue"),
        ("catalogue", "0002_peupler_catalogue_depuis_public"),
    ]

    operations = [
        migrations.RunPython(reparenter_overrides_vers_catalogue, reverse_code=annuler_reparentage),
    ]
