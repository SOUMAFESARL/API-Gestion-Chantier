"""Synchronise les permissions GED et Stock et peuple les défauts F6 sur les rôles système."""

from django.db import migrations


def synchroniser_droits_ged(apps, schema_editor):
    from apps.accounts.services.roles import PERMISSIONS_DEFAUT_ROLES
    from apps.core.contexte import contexte_entreprise
    from apps.core.enums import MODULES_DETAILS, ModuleChoix
    from apps.core.registre_permissions import REGISTRE

    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")
    Entreprise = apps.get_model("entreprises", "Entreprise")
    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")

    libelles_modules = dict(ModuleChoix.choices)
    modules_map = {}

    for mod_code, libelle in libelles_modules.items():
        details = MODULES_DETAILS.get(mod_code, {})
        module, _ = CatalogueModule.objects.get_or_create(
            code=mod_code,
            defaults={
                "libelle": libelle,
                "description": details.get("description", ""),
                "ordre": details.get("ordre", 1),
                "icone": details.get("icone", "box"),
                "est_actif": True,
            },
        )
        modules_map[mod_code] = module

    perms_map = {}
    for code, def_perm in REGISTRE.items():
        module = modules_map.get(def_perm.module)
        if module is None:
            module, _ = CatalogueModule.objects.get_or_create(
                code=def_perm.module,
                defaults={
                    "libelle": def_perm.module.capitalize(),
                    "ordre": 1,
                    "est_actif": True,
                },
            )
            modules_map[def_perm.module] = module

        perm = CataloguePermission.objects.filter(code=code, supprime_le__isnull=True).first()
        if perm is None:
            perm = CataloguePermission.objects.create(
                code=code,
                libelle=def_perm.libelle,
                description=def_perm.libelle,
                ordre=def_perm.rang,
                est_actif=True,
                reservee_administration=def_perm.reservee_administration,
            )
            perm.modules.set([module])
        else:
            champs = []
            if perm.libelle != def_perm.libelle:
                perm.libelle = def_perm.libelle
                champs.append("libelle")
            if perm.ordre != def_perm.rang:
                perm.ordre = def_perm.rang
                champs.append("ordre")
            if not perm.est_actif:
                perm.est_actif = True
                champs.append("est_actif")
            if champs:
                perm.save(update_fields=champs)
            if not perm.modules.filter(id=module.id).exists():
                perm.modules.set([module])

        perms_map[code] = perm

    mod_ged = modules_map.get("ged")
    if mod_ged is None:
        return

    for entreprise in Entreprise.objects.all():
        with contexte_entreprise(entreprise):
            roles_systeme = Role.objects.filter(
                entreprise=entreprise,
                est_systeme=True,
                supprime_le__isnull=True,
            )
            for role in roles_systeme:
                r_code = (role.code or "").strip().upper()
                for mod_code, mod_obj in modules_map.items():
                    if mod_code not in ("ged", "stock"):
                        continue
                    rmp, _ = RoleModulePermission.objects.get_or_create(
                        entreprise=entreprise,
                        role=role,
                        module_catalogue=mod_obj,
                        supprime_le__isnull=True,
                    )
                    # Peupler uniquement les lignes restées vides lors de l'introduction de F6/F9
                    if rmp.permissions_catalogue.count() == 0:
                        codes = PERMISSIONS_DEFAUT_ROLES.get(r_code, {}).get(mod_code, ())
                        perms = [perms_map[c] for c in codes if c in perms_map]
                        if perms:
                            rmp.permissions_catalogue.set(perms)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
        ("catalogue", "0001_initial"),
        ("entreprises", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(synchroniser_droits_ged, migrations.RunPython.noop),
    ]
