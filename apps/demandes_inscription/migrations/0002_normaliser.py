from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('demandes_inscription', '0001_initial')]

    operations = [
        migrations.RunSQL(
            sql=r"""
                CREATE OR REPLACE FUNCTION demande_inscription_normaliser()
                RETURNS trigger AS $$
                BEGIN
                    IF NEW.raison_sociale IS NOT NULL THEN
                        NEW.raison_sociale := regexp_replace(btrim(NEW.raison_sociale), '\s+', ' ', 'g');
                    END IF;
                    IF NEW.email IS NOT NULL THEN
                        NEW.email := lower(btrim(NEW.email));
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER trg_demande_inscription_normaliser
                BEFORE INSERT OR UPDATE ON demande_inscription
                FOR EACH ROW EXECUTE FUNCTION demande_inscription_normaliser();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS trg_demande_inscription_normaliser ON demande_inscription;
                DROP FUNCTION IF EXISTS demande_inscription_normaliser();
            """,
        ),
    ]
