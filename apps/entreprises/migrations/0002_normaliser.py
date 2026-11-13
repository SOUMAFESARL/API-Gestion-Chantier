from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('entreprises', '0001_initial')]

    operations = [
        migrations.RunSQL(
            sql=r"""
                CREATE OR REPLACE FUNCTION entreprise_normaliser()
                RETURNS trigger AS $$
                BEGIN
                    IF NEW.raison_sociale IS NOT NULL THEN
                        NEW.raison_sociale := regexp_replace(btrim(NEW.raison_sociale), '\s+', ' ', 'g');
                    END IF;
                    IF NEW.email_contact IS NOT NULL THEN
                        NEW.email_contact := lower(btrim(NEW.email_contact));
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER trg_entreprise_normaliser
                BEFORE INSERT OR UPDATE ON entreprise
                FOR EACH ROW EXECUTE FUNCTION entreprise_normaliser();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS trg_entreprise_normaliser ON entreprise;
                DROP FUNCTION IF EXISTS entreprise_normaliser();
            """,
        ),
    ]
