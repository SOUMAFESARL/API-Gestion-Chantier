"""Migration de données tenant pour appliquer les niveaux des gabarits aux rôles existants."""

from django.db import migrations


def appliquer_modeles_niveaux_tenant(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name == "public":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'role_module_permission'
            );
        """)
        if not cursor.fetchone()[0]:
            return

        # 1. Aligner les niveaux selon les plafonds des modèles de rôles
        cursor.execute("""
            UPDATE role_module_permission rmp
            SET niveau = cmrm.niveau_max
            FROM role r, catalogue_modele_role cmr, catalogue_modele_role_module cmrm, module m
            WHERE rmp.role_id = r.id
              AND UPPER(r.code) = UPPER(cmr.code)
              AND cmrm.modele_role_id = cmr.id
              AND rmp.module_id = m.id
              AND LOWER(cmrm.module_code) = LOWER(m.code);
        """)

        # 2. Le rôle DG a toujours niveau 3 (Validation)
        cursor.execute("""
            UPDATE role_module_permission rmp
            SET niveau = 3
            FROM role r
            WHERE rmp.role_id = r.id
              AND UPPER(r.code) = 'DG';
        """)

        # 3. Synchroniser les tables de permissions selon le niveau
        # Pour niveau 0 : vider les liaisons
        cursor.execute("""
            DELETE FROM role_module_permission_permissions rmpp
            USING role_module_permission rmp
            WHERE rmpp.rolemodulepermission_id = rmp.id AND rmp.niveau = 0;
        """)
        cursor.execute("""
            DELETE FROM role_module_permission_permissions_catalogue rmppc
            USING role_module_permission rmp
            WHERE rmppc.rolemodulepermission_id = rmp.id AND rmp.niveau = 0;
        """)

        # Pour niveau 1 (Lecture seule) : supprimer ECRITURE et VALIDATION
        cursor.execute("""
            DELETE FROM role_module_permission_permissions rmpp
            USING role_module_permission rmp, permission p
            WHERE rmpp.rolemodulepermission_id = rmp.id 
              AND rmpp.permission_id = p.id
              AND rmp.niveau = 1
              AND UPPER(p.code) IN ('ECRITURE', 'VALIDATION');
        """)
        cursor.execute("""
            DELETE FROM role_module_permission_permissions_catalogue rmppc
            USING role_module_permission rmp, catalogue_permission cp
            WHERE rmppc.rolemodulepermission_id = rmp.id 
              AND rmppc.cataloguepermission_id = cp.id
              AND rmp.niveau = 1
              AND UPPER(cp.code) IN ('ECRITURE', 'VALIDATION');
        """)

        # Pour niveau 2 : supprimer VALIDATION
        cursor.execute("""
            DELETE FROM role_module_permission_permissions rmpp
            USING role_module_permission rmp, permission p
            WHERE rmpp.rolemodulepermission_id = rmp.id 
              AND rmpp.permission_id = p.id
              AND rmp.niveau = 2
              AND UPPER(p.code) = 'VALIDATION';
        """)
        cursor.execute("""
            DELETE FROM role_module_permission_permissions_catalogue rmppc
            USING role_module_permission rmp, catalogue_permission cp
            WHERE rmppc.rolemodulepermission_id = rmp.id 
              AND rmppc.cataloguepermission_id = cp.id
              AND rmp.niveau = 2
              AND UPPER(cp.code) = 'VALIDATION';
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_purger_emails_test_duzanf_schema_public"),
        ("catalogue", "0004_peupler_modeles_roles"),
    ]

    operations = [
        migrations.RunPython(appliquer_modeles_niveaux_tenant, noop),
    ]
