"""Migration de données pour initialiser les 10 modèles de rôles souverains et leurs plafonds par module."""

from django.db import migrations

MODELES_ROLES_DATA = [
    {
        "code": "DG",
        "libelle": "Directeur Général / PDG",
        "description": "Supervision globale, décisions stratégiques et vision consolidée de tous les projets",
        "modules": {
            "projets": 3,
            "chantier": 3,
            "ged": 3,
            "pilotage": 3,
            "tiers": 3,
            "administration": 3,
        },
    },
    {
        "code": "AD",
        "libelle": "Administrateur",
        "description": "Paramétrage de l'organisation, administration technique et gestion des utilisateurs",
        "modules": {
            "projets": 3,
            "chantier": 3,
            "ged": 3,
            "pilotage": 2,
            "tiers": 2,
            "administration": 2,
        },
    },
    {
        "code": "DO",
        "libelle": "Directeur des Opérations",
        "description": "Pilotage opérationnel multi-chantiers et coordination des équipes techniques",
        "modules": {
            "projets": 3,
            "chantier": 3,
            "ged": 3,
            "pilotage": 2,
            "tiers": 2,
            "administration": 0,
        },
    },
    {
        "code": "DF",
        "libelle": "Directeur Financier / DAF",
        "description": "Suivi budgétaire, rentabilité, facturation et vision financière consolidée",
        "modules": {
            "projets": 1,
            "chantier": 1,
            "ged": 2,
            "pilotage": 3,
            "tiers": 2,
            "administration": 0,
        },
    },
    {
        "code": "CP",
        "libelle": "Chef de Projet",
        "description": "Pilotage opérationnel des projets qui lui sont confiés et accès complet à ses chantiers",
        "modules": {
            "projets": 2,
            "chantier": 2,
            "ged": 2,
            "pilotage": 1,
            "tiers": 1,
            "administration": 0,
        },
    },
    {
        "code": "CT",
        "libelle": "Conducteur de Travaux",
        "description": "Supervision quotidienne, coordination des équipes terrain et validation technique",
        "modules": {
            "projets": 2,
            "chantier": 3,
            "ged": 2,
            "pilotage": 1,
            "tiers": 1,
            "administration": 0,
        },
    },
    {
        "code": "CC",
        "libelle": "Chef de Chantier",
        "description": "Saisie terrain : avancement, incidents, photos, pointage",
        "modules": {
            "projets": 1,
            "chantier": 2,
            "ged": 1,
            "pilotage": 0,
            "tiers": 0,
            "administration": 0,
        },
    },
    {
        "code": "MAG",
        "libelle": "Magasinier / Gestionnaire de Stock",
        "description": "Gestion des approvisionnements, réceptions de matériaux et sorties de stock",
        "modules": {
            "projets": 0,
            "chantier": 1,
            "ged": 1,
            "pilotage": 0,
            "tiers": 2,
            "administration": 0,
        },
    },
    {
        "code": "BAI",
        "libelle": "Bailleur / Client / MOA",
        "description": "Suivi de l'avancement global du chantier et consultation des rapports d'activité",
        "modules": {
            "projets": 1,
            "chantier": 1,
            "ged": 1,
            "pilotage": 1,
            "tiers": 0,
            "administration": 0,
        },
    },
    {
        "code": "VI",
        "libelle": "Visiteur / Auditeur",
        "description": "Consultation de l'avancement et des données du chantier en lecture seule",
        "modules": {
            "projets": 1,
            "chantier": 1,
            "ged": 1,
            "pilotage": 1,
            "tiers": 0,
            "administration": 0,
        },
    },
]


def peupler_modeles_roles(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return

    ModeleRole = apps.get_model("catalogue", "ModeleRole")
    ModeleRoleModule = apps.get_model("catalogue", "ModeleRoleModule")
    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")

    modules_par_code = {m.code.lower(): m for m in CatalogueModule.objects.all()}

    for role_data in MODELES_ROLES_DATA:
        modele, _ = ModeleRole.objects.update_or_create(
            code=role_data["code"],
            defaults={
                "libelle": role_data["libelle"],
                "description": role_data["description"],
                "est_actif": True,
            },
        )
        for mod_code, niveau_max in role_data["modules"].items():
            cat_mod = modules_par_code.get(mod_code.lower())
            ModeleRoleModule.objects.update_or_create(
                modele_role=modele,
                module_code=mod_code.lower(),
                defaults={
                    "module": cat_mod,
                    "niveau_max": niveau_max,
                },
            )


def reverser_modeles_roles(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name != "public":
        return
    ModeleRole = apps.get_model("catalogue", "ModeleRole")
    ModeleRole.objects.filter(code__in=[r["code"] for r in MODELES_ROLES_DATA]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0003_modelerole_modelerolemodule_and_more"),
    ]

    operations = [
        migrations.RunPython(peupler_modeles_roles, reverser_modeles_roles),
    ]
