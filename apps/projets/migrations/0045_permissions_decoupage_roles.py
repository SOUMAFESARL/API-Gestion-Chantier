"""Donne aux rôles système existants les permissions du découpage qu'ils ont par défaut.

Défauts validés le 29/10/2026 : découper, chiffrer et prolonger au chef de projet ; planifier,
mesurer, retirer un membre et gérer le registre de main-d'œuvre au chef de projet et au
conducteur de travaux ; voir tout le projet aux rôles qui le voyaient déjà en entier. Le DG a
toutes les permissions sans qu'on les coche.

**On ajoute, on ne retire rien** : une entreprise dont le DG a déjà réglé ses rôles garde ses
réglages, elle reçoit seulement les nouvelles cases cochées par défaut.
"""

from django.db import migrations

DEFAUTS = {
    "CP": [
        "projets.voir_tout",
        "projets.decouper",
        "projets.chiffrer",
        "projets.planifier",
        "projets.prolonger",
        "projets.mesurer",
        "projets.retirer_membres",
        "projets.main_oeuvre_gerer",
    ],
    "CT": [
        "projets.voir_tout",
        "projets.planifier",
        "projets.mesurer",
        "projets.retirer_membres",
        "projets.main_oeuvre_gerer",
    ],
    "DF": ["projets.voir_tout"],
    "BAI": ["projets.voir_tout"],
    "VI": ["projets.voir_tout"],
}


def donner(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") == "public":
        return
    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")
    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")
    module = CatalogueModule.objects.filter(code="projets", supprime_le__isnull=True).first()
    if module is None:
        return
    perms = {
        p.code: p
        for p in CataloguePermission.objects.filter(
            code__in={c for codes in DEFAUTS.values() for c in codes}, supprime_le__isnull=True
        )
    }
    for code_role, codes in DEFAUTS.items():
        for role in Role.objects.filter(code=code_role, est_systeme=True, supprime_le__isnull=True):
            rmp = RoleModulePermission.objects.filter(
                role=role, module_catalogue=module, supprime_le__isnull=True
            ).first()
            if rmp is None:
                continue
            rmp.permissions_catalogue.add(*[perms[c] for c in codes if c in perms])


class Migration(migrations.Migration):
    dependencies = [
        ("projets", "0044_equipes_main_oeuvre"),
        ("catalogue", "0015_permissions_decoupage"),
        ("accounts", "0032_permission_referentiels_ajouter"),
    ]

    operations = [
        migrations.RunPython(donner, migrations.RunPython.noop),
    ]
