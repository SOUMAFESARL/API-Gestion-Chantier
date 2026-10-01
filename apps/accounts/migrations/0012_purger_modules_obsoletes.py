# Migration 0012 — Purger les RoleModulePermission orphelines
#
# Le ModuleChoix a été réduit de 12 à 5 modules souverains, mais les
# entrées RoleModulePermission correspondant aux 7 anciens modules
# (finance, achats, stocks, rh, equipements, qhse, contrats) n'ont
# jamais été supprimées en production. Cette migration les purge pour
# TOUS les rôles (système + personnalisés).

from django.db import migrations

# Les 5 modules actuels définis dans ModuleChoix
MODULES_ACTUELS = {"projets", "chantier", "ged", "pilotage", "tiers"}

# Les 7 modules obsolètes à supprimer
MODULES_OBSOLETES = {
    "finance", "achats", "stocks", "rh",
    "equipements", "qhse", "contrats",
}


def purger_modules_obsoletes(apps, schema_editor):
    """Supprime les RoleModulePermission dont le module n'existe plus."""
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    nb, _ = RoleModulePermission.objects.filter(
        module__in=MODULES_OBSOLETES,
    ).delete()
    if nb:
        print(f"\n    -> {nb} permission(s) de modules obsoletes supprimee(s).")


def restaurer_modules_obsoletes(apps, schema_editor):
    """Rollback : recrée les permissions des modules obsolètes avec niveau=3 (VALIDATION).

    NB : Cette restauration est approximative car les niveaux originaux
    ne sont pas conservés. Tous les modules restaurés reçoivent le
    niveau VALIDATION (3) par défaut.
    """
    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")

    NIVEAU_VALIDATION = 3
    objets = []
    for role in Role.objects.all():
        for module in MODULES_OBSOLETES:
            objets.append(RoleModulePermission(
                role=role,
                module=module,
                niveau=NIVEAU_VALIDATION,
            ))
    if objets:
        RoleModulePermission.objects.bulk_create(objets, ignore_conflicts=True)
        print(f"\n    -> {len(objets)} permission(s) de modules obsoletes restauree(s).")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_restreindre_est_systeme_dg_admin"),
    ]

    operations = [
        migrations.RunPython(
            purger_modules_obsoletes,
            reverse_code=restaurer_modules_obsoletes,
        ),
    ]
