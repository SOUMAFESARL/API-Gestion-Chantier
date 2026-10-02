from django.db import migrations


def purger_utilisateurs_duzanf_public(apps, schema_editor):
    connection = schema_editor.connection
    schema_name = getattr(connection, "schema_name", "public")
    # Cette opération cible STRICTEMENT le schéma public
    if schema_name != "public":
        return

    cibles_sql = "'duzanf@gmail.com', 'duzanf2@gmail.com'"
    with connection.cursor() as cursor:
        # 1. Neutraliser les contraintes FK pointant vers public.utilisateur
        cursor.execute(
            """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND ccu.table_name = 'utilisateur'
            """
        )
        fks = cursor.fetchall()
        for table, col in fks:
            try:
                cursor.execute(
                    f"""
                    UPDATE public."{table}"
                    SET "{col}" = NULL
                    WHERE "{col}" IN (
                        SELECT id FROM public.utilisateur WHERE LOWER(email) IN ({cibles_sql})
                    )
                    """
                )
            except Exception as e:
                print(f"[PURGE] FK {table}.{col} non mise a jour : {e}")

        # 2. Supprimer les comptes résiduels du schéma public
        cursor.execute(
            f"""
            DELETE FROM public.utilisateur
            WHERE LOWER(email) IN ({cibles_sql})
            """
        )
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"\n[PURGE] {deleted} compte(s) residuel(s) supprime(s) du schema public.")


def inverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0020_repointer_rolemodulepermission_vers_catalogue"),
    ]

    operations = [
        migrations.RunPython(purger_utilisateurs_duzanf_public, inverse),
    ]
