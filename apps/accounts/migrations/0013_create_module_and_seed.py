# Generated for dynamic Module catalog architecture

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MODULES_INITIAUX = [
    {
        "code": "projets",
        "libelle": "Gestion des Projets",
        "description": "Fiches projets, lots, activités, jalons et planification des chantiers.",
        "ordre": 1,
        "icone": "folder-kanban",
        "est_actif": True,
    },
    {
        "code": "chantier",
        "libelle": "Suivi Technique / Chantier",
        "description": "Rapports journaliers, avancement des travaux, blocages terrain et pointages.",
        "ordre": 2,
        "icone": "hard-hat",
        "est_actif": True,
    },
    {
        "code": "ged",
        "libelle": "Gestion Documentaire (GED)",
        "description": "Classeurs, plans d'exécution, procès-verbaux et traçabilité des pièces jointes.",
        "ordre": 3,
        "icone": "file-text",
        "est_actif": True,
    },
    {
        "code": "pilotage",
        "libelle": "Tableaux de bord & Pilotage",
        "description": "Indicateurs d'avancement, indice de santé global, météo et aide à la décision.",
        "ordre": 4,
        "icone": "bar-chart-3",
        "est_actif": True,
    },
    {
        "code": "tiers",
        "libelle": "Parties Prenantes / Tiers",
        "description": "Clients, maîtres d'ouvrage, sous-traitants, fournisseurs et partenaires.",
        "ordre": 5,
        "icone": "users",
        "est_actif": True,
    },
]


def seed_modules(apps, schema_editor):
    Module = apps.get_model("accounts", "Module")
    for data in MODULES_INITIAUX:
        Module.objects.update_or_create(
            code=data["code"],
            defaults=data,
        )


def unseed_modules(apps, schema_editor):
    Module = apps.get_model("accounts", "Module")
    codes = [d["code"] for d in MODULES_INITIAUX]
    Module.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_purger_modules_obsoletes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Module",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "cree_le",
                    models.DateTimeField(auto_now_add=True, verbose_name="créé le"),
                ),
                (
                    "modifie_le",
                    models.DateTimeField(auto_now=True, verbose_name="modifié le"),
                ),
                (
                    "supprime_le",
                    models.DateTimeField(
                        blank=True,
                        db_index=True,
                        help_text="Non nul = ligne supprimée logiquement. Jamais de suppression physique.",
                        null=True,
                        verbose_name="supprimé le",
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        db_index=True,
                        help_text="Code technique unique du module (ex: 'projets', 'chantier', 'ged').",
                        max_length=30,
                        verbose_name="code",
                    ),
                ),
                (
                    "libelle",
                    models.CharField(
                        help_text="Nom officiel et lisible du module.",
                        max_length=100,
                        verbose_name="libellé",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Périmètre fonctionnel et fonctionnalités couvertes par ce module.",
                        verbose_name="description",
                    ),
                ),
                (
                    "ordre",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Position ordonnée dans la navigation et les matrices de permissions.",
                        verbose_name="ordre d'affichage",
                    ),
                ),
                (
                    "icone",
                    models.CharField(
                        blank=True,
                        default="box",
                        help_text="Identifiant de l'icône Lucide / frontend associée.",
                        max_length=50,
                        verbose_name="icône",
                    ),
                ),
                (
                    "est_actif",
                    models.BooleanField(
                        default=True,
                        help_text="Indique si le module est disponible dans ce tenant.",
                        verbose_name="est actif",
                    ),
                ),
                (
                    "cree_par",
                    models.ForeignKey(
                        blank=True,
                        help_text="Nul lorsque l'écriture vient du système.",
                        null=True,
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="créé par",
                    ),
                ),
                (
                    "supprime_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="supprimé par",
                    ),
                ),
            ],
            options={
                "verbose_name": "module",
                "verbose_name_plural": "modules",
                "db_table": "module",
                "ordering": ["ordre", "code"],
            },
        ),
        migrations.AddConstraint(
            model_name="module",
            constraint=models.UniqueConstraint(
                condition=models.Q(supprime_le__isnull=True),
                fields=("code",),
                name="uq_module_code_actif",
            ),
        ),
        migrations.RunPython(
            seed_modules,
            reverse_code=unseed_modules,
        ),
    ]
