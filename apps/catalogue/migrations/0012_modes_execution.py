"""Le mode d'exécution d'un lot devient un référentiel (plateforme + entreprise).

Les trois modes de l'ancienne énumération `ModeExecution` deviennent trois entrées de la
plateforme : même code, même libellé, et `groupe` = le code lui-même (un mode de base se
rattache à lui-même). Les modes ajoutés ensuite se rattachent obligatoirement à l'un d'eux.
"""

from django.db import migrations, models

MODES = [
    ("REGIE", "Régie"),
    ("SOUS_TRAITANCE_STRUCTUREE", "Sous-traitance structurée"),
    ("SOUS_TRAITANCE_INFORMELLE", "Sous-traitance informelle"),
]


def peupler(apps, schema_editor):
    referentiel = apps.get_model("catalogue", "ReferentielPlateforme")
    for ordre, (code, libelle) in enumerate(MODES):
        referentiel.objects.get_or_create(
            categorie="MODE_EXECUTION",
            code=code,
            supprime_le__isnull=True,
            defaults={"libelle": libelle, "groupe": code, "ordre": ordre},
        )


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0011_peupler_referentiels")]

    operations = [
        migrations.AlterField(
            model_name="referentielplateforme",
            name="categorie",
            field=models.CharField(
                choices=[
                    ("TYPE_PROJET", "Type de projet"),
                    ("LOT", "Nom de lot"),
                    ("MODE_EXECUTION", "Mode d'exécution"),
                ],
                max_length=20,
                verbose_name="catégorie",
            ),
        ),
        migrations.AlterField(
            model_name="referentielplateforme",
            name="groupe",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Titre de groupe dans la liste — le corps d'état d'un lot ; "
                    "pour un mode d'exécution, le mode de base auquel il se rattache."
                ),
                max_length=100,
                verbose_name="groupe",
            ),
        ),
        migrations.RunPython(peupler, migrations.RunPython.noop),
    ]
