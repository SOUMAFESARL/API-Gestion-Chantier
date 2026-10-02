"""Migration de données pour reparenter RoleModulePermission vers catalogue_module et catalogue_permission."""

from django.db import migrations


def reparenter_vers_catalogue(apps, schema_editor):
    cursor = schema_editor.connection.cursor()

    # Vérifier si les tables locales nécessaires existent dans ce schéma
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'role_module_permission'
        );
    """)
    if not cursor.fetchone()[0]:
        return

    # 1. Reparentage de module_catalogue_id par matching sur le code
    cursor.execute("""
        UPDATE role_module_permission rmp
        SET module_catalogue_id = cm.id
        FROM module m, catalogue_module cm
        WHERE rmp.module_id = m.id
          AND m.code = cm.code
          AND rmp.module_catalogue_id IS NULL;
    """)

    # 2. Vérification d'intégrité : 0 orphelins non migrés
    cursor.execute("""
        SELECT COUNT(*)
        FROM role_module_permission
        WHERE module_id IS NOT NULL AND module_catalogue_id IS NULL;
    """)
    orphelins = cursor.fetchone()[0]
    if orphelins > 0:
        raise ValueError(
            f"ERREUR FATALE : {orphelins} ligne(s) de role_module_permission n'ont pas pu "
            f"être associées au catalogue partagé."
        )

    # 3. Migration de la table de liaison permissions -> permissions_catalogue
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'role_module_permission_permissions'
        );
    """)
    if cursor.fetchone()[0]:
        cursor.execute("""
            INSERT INTO role_module_permission_permissions_catalogue (
                rolemodulepermission_id, cataloguepermission_id
            )
            SELECT rmpp.rolemodulepermission_id, cp.id
            FROM role_module_permission_permissions rmpp
            JOIN permission p ON rmpp.permission_id = p.id
            JOIN catalogue_permission cp ON p.code = cp.code
            ON CONFLICT DO NOTHING;
        """)


def annuler_reparentage(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    cursor.execute("""
        UPDATE role_module_permission
        SET module_catalogue_id = NULL;
    """)
    cursor.execute("""
        DELETE FROM role_module_permission_permissions_catalogue;
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0019_rolemodulepermission_module_catalogue_and_more"),
        ("catalogue", "0002_peupler_catalogue_depuis_public"),
    ]

    operations = [
        migrations.RunPython(reparenter_vers_catalogue, reverse_code=annuler_reparentage),
    ]
