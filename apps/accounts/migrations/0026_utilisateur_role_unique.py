import django.db.models.deletion
from django.db import migrations, models


def migrer_utilisateurs_vers_role_unique(apps, schema_editor):
    """Migre tous les collaborateurs vers le champ unique role (B-01).

    Traduit MOA -> BAI et MOE -> VI.
    Assigne le rôle unique à chaque collaborateur.
    """
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name == "public":
        return

    Utilisateur = apps.get_model("accounts", "Utilisateur")
    Role = apps.get_model("accounts", "Role")

    # Mappage des anciens rôles
    mapping_roles = {
        "MOA": "BAI",
        "MOE": "VI",
    }

    # Supprimer ou marquer supprimés les rôles MOA/MOE s'ils existent dans ce tenant
    Role.objects.filter(code__in=["MOA", "MOE"]).update(est_actif=False)

    for user in Utilisateur.objects.all():
        role_trouve = None

        # 1. Si rôle personnalisé était renseigné
        if getattr(user, "role_personnalise_id", None):
            role_trouve = Role.objects.filter(id=user.role_personnalise_id, supprime_le__isnull=True).first()

        # 2. Sinon déduire depuis role_global
        if not role_trouve and getattr(user, "role_global", None):
            code_brut = user.role_global
            code_mappe = mapping_roles.get(code_brut, code_brut)
            role_trouve = Role.objects.filter(code=code_mappe, supprime_le__isnull=True).first()

        if role_trouve:
            user.role = role_trouve
            user.role_global = role_trouve.code
            user.save(update_fields=["role", "role_global"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_supprimer_permissions_m2m_rolemodulepermission"),
    ]

    operations = [
        migrations.AddField(
            model_name="utilisateur",
            name="role",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="collaborateurs",
                to="accounts.role",
                verbose_name="rôle",
            ),
        ),
        migrations.AlterField(
            model_name="utilisateur",
            name="role_global",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="VISITEUR",
                max_length=50,
                verbose_name="rôle global",
            ),
        ),
        migrations.AlterField(
            model_name="invitation",
            name="role_propose",
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name="rôle proposé",
            ),
        ),
        migrations.RunPython(migrer_utilisateurs_vers_role_unique, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="utilisateur",
            name="role_personnalise",
        ),
    ]
