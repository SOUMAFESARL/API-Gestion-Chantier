"""Les permissions du découpage en arbre, dans le catalogue public (décisions v1.2, §13bis).

Le déploiement synchronise ensuite le catalogue depuis le registre
(`synchroniser_catalogue_permissions`), mais cette commande passe **après** les migrations : sans
les permissions ici, la migration des entreprises (`projets.0045`) ne trouverait rien à donner
aux rôles existants.
"""

from django.db import migrations

PERMISSIONS = [
    ("projets.voir_tout", "Voir tout le projet, hors de son périmètre", 1),
    (
        "projets.decouper",
        "Découper le projet (ajouter, déplacer, détailler, insérer un niveau, désactiver)",
        2,
    ),
    ("projets.chiffrer", "Fixer les montants et les quantités prévues", 2),
    ("projets.planifier", "Planifier et reprogrammer les dates", 2),
    ("projets.prolonger", "Prolonger le projet ou une case déjà commencée", 3),
    ("projets.mesurer", "Mesurer l'avancement hors du journal", 2),
    ("projets.retirer_membres", "Retirer un membre du projet", 2),
    ("projets.main_oeuvre_gerer", "Gérer le registre de main-d'œuvre", 2),
    ("projets.modeles_gerer", "Gérer les listes et les modèles de découpage de l'entreprise", 3),
]


def creer(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    Module = apps.get_model("catalogue", "CatalogueModule")
    Permission = apps.get_model("catalogue", "CataloguePermission")
    module = Module.objects.filter(code="projets", supprime_le__isnull=True).first()
    if module is None:
        module = Module.objects.create(code="projets", libelle="Projets", ordre=1, est_actif=True)
    for code, libelle, ordre in PERMISSIONS:
        perm = Permission.objects.filter(code=code, supprime_le__isnull=True).first()
        if perm is None:
            perm = Permission.objects.create(
                code=code, libelle=libelle, description=libelle, ordre=ordre, est_actif=True
            )
        perm.modules.add(module)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0014_peupler_decoupage"),
    ]

    operations = [
        migrations.RunPython(creer, migrations.RunPython.noop),
    ]
