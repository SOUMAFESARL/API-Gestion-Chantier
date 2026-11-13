from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('entreprises', '0003_telephoneentreprise')]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE telephone_entreprise ENABLE ROW LEVEL SECURITY;
                CREATE POLICY telephone_entreprise_isolation
                ON telephone_entreprise
                USING (entreprise_id = current_setting('app.entreprise_id', true)::uuid);
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS telephone_entreprise_isolation ON telephone_entreprise;
                ALTER TABLE telephone_entreprise DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
