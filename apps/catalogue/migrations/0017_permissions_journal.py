"""Les permissions qui désignent les fonctions du journal et des alertes (30/10/2026).

Le circuit ne lit plus le nom des rôles : celui qui a « rédiger » écrit son rapport, ceux qui
ont « valider » puis « approuver » le signent, et les alertes vont à ceux qui ont la permission
de leur niveau. Créées ici pour que la migration des entreprises (`projets.0047`) les trouve.
"""

from django.db import migrations

PERMISSIONS = [
    ("chantier", "chantier.approuver", "Approuver un rapport", 4),
    ("chantier", "chantier.synthese_rediger", "Rédiger la synthèse de la semaine", 5),
    ("chantier", "chantier.synthese_approuver", "Approuver la synthèse de la semaine", 6),
    ("projets", "projets.alertes_moderees", "Recevoir les alertes de retard modérées", 1),
    ("projets", "projets.alertes_elevees", "Recevoir les alertes de retard élevées", 1),
    ("projets", "projets.alertes_critiques", "Recevoir les alertes de retard critiques", 1),
]


def creer(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    Module = apps.get_model("catalogue", "CatalogueModule")
    Permission = apps.get_model("catalogue", "CataloguePermission")
    for code_module, code, libelle, ordre in PERMISSIONS:
        module = Module.objects.filter(code=code_module, supprime_le__isnull=True).first()
        if module is None:
            continue
        perm = Permission.objects.filter(code=code, supprime_le__isnull=True).first()
        if perm is None:
            perm = Permission.objects.create(
                code=code, libelle=libelle, description=libelle, ordre=ordre, est_actif=True
            )
        perm.modules.add(module)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0016_modelerole_unique_par_projet"),
    ]

    operations = [
        migrations.RunPython(creer, migrations.RunPython.noop),
    ]
