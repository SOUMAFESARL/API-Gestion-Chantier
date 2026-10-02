"""Migration de données pour peupler le catalogue partagé depuis les tables public."""

from django.db import migrations


def migrer_catalogue(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return

    db_alias = schema_editor.connection.alias
    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")
    EntrepriseModule = apps.get_model("catalogue", "EntrepriseModule")
    Entreprise = apps.get_model("tenants", "Entreprise")

    with schema_editor.connection.cursor() as cursor:
        # Vérifier si la table public.module existe et contient des lignes
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'module'
            );
        """)
        table_module_existe = cursor.fetchone()[0]

        if table_module_existe:
            cursor.execute("""
                INSERT INTO catalogue_module (
                    id, code, libelle, description, ordre, icone, est_actif,
                    cree_le, modifie_le, cree_par_id, supprime_le, supprime_par_id
                )
                SELECT 
                    id, code, libelle, description, ordre, icone, est_actif,
                    cree_le, modifie_le, cree_par_id, supprime_le, supprime_par_id
                FROM public.module
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code,
                    libelle = EXCLUDED.libelle,
                    description = EXCLUDED.description,
                    ordre = EXCLUDED.ordre,
                    icone = EXCLUDED.icone,
                    est_actif = EXCLUDED.est_actif;
            """)

        # Vérifier si la table public.permission existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'permission'
            );
        """)
        table_perm_existe = cursor.fetchone()[0]

        if table_perm_existe:
            cursor.execute("""
                INSERT INTO catalogue_permission (
                    id, code, libelle, description, ordre, est_actif,
                    cree_le, modifie_le, cree_par_id, supprime_le, supprime_par_id
                )
                SELECT 
                    id, code, libelle, description, ordre, est_actif,
                    cree_le, modifie_le, cree_par_id, supprime_le, supprime_par_id
                FROM public.permission
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code,
                    libelle = EXCLUDED.libelle,
                    description = EXCLUDED.description,
                    ordre = EXCLUDED.ordre,
                    est_actif = EXCLUDED.est_actif;
            """)

        # Vérifier si la table de liaison public.permission_modules existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'permission_modules'
            );
        """)
        table_m2m_existe = cursor.fetchone()[0]

        if table_m2m_existe:
            cursor.execute("""
                INSERT INTO catalogue_permission_modules (cataloguepermission_id, cataloguemodule_id)
                SELECT permission_id, module_id
                FROM public.permission_modules
                ON CONFLICT DO NOTHING;
            """)

    # Initialisation de catalogue_entreprise_module pour chaque entreprise cliente
    entreprises = Entreprise.objects.using(db_alias).exclude(schema_name="public")
    modules = list(CatalogueModule.objects.using(db_alias).filter(supprime_le__isnull=True))

    for e in entreprises:
        for m in modules:
            EntrepriseModule.objects.using(db_alias).get_or_create(
                entreprise=e,
                module=m,
                defaults={"est_actif": m.est_actif}
            )


def annuler_migration(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return
    db_alias = schema_editor.connection.alias
    apps.get_model("catalogue", "EntrepriseModule").objects.using(db_alias).all().delete()
    apps.get_model("catalogue", "CataloguePermission").objects.using(db_alias).all().delete()
    apps.get_model("catalogue", "CatalogueModule").objects.using(db_alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0001_initial"),
        ("accounts", "0001_squashed_0018_seed_permission_modules_m2m"),
        ("tenants", "0010_remove_demandeinscription_uq_demande_slug_and_more"),
    ]

    operations = [
        migrations.RunPython(migrer_catalogue, reverse_code=annuler_migration),
    ]
