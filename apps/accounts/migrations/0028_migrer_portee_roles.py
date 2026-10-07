from django.db import migrations


def migrer_portee_roles(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name == "public":
        return

    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    ModeleRole = apps.get_model("catalogue", "ModeleRole")

    roles_systeme = ["DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"]
    for mr in ModeleRole.objects.filter(code__in=roles_systeme):
        Role.objects.update_or_create(
            code=mr.code,
            defaults={
                "libelle": mr.libelle,
                "description": mr.description,
                "est_systeme": True,
                "portee": mr.portee,
                "est_actif": True,
            },
        )

    # Désactiver les anciens rôles obsolètes
    Role.objects.filter(code__in=["MOA", "MOE"]).update(est_actif=False, est_systeme=False)

    roles_entreprise = {"DG", "AD", "DO"}
    Role.objects.filter(code__in=roles_entreprise).update(portee="ENTREPRISE")

    # Tout rôle ayant projets.voir_tous dans ses permissions
    rmps_voir_tous = RoleModulePermission.objects.filter(
        permissions_catalogue__code="projets.voir_tous",
        supprime_le__isnull=True,
    ).values_list("role_id", flat=True)

    if rmps_voir_tous:
        Role.objects.filter(id__in=rmps_voir_tous).update(portee="ENTREPRISE")

    # Tous les autres rôles sont fixés à PROJET
    Role.objects.exclude(code__in=roles_entreprise).exclude(id__in=rmps_voir_tous).update(portee="PROJET")

    # Fixer strictement est_systeme=True uniquement sur les 10 rôles souverains
    Role.objects.filter(code__in=roles_systeme).update(est_systeme=True)
    Role.objects.exclude(code__in=roles_systeme).update(est_systeme=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0027_role_portee"),
        ("catalogue", "0008_modelerole_portee"),
    ]

    operations = [
        migrations.RunPython(migrer_portee_roles, migrations.RunPython.noop),
    ]
