"""L'unicité d'un rôle sur un projet devient un réglage du rôle (30/10/2026)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projets", "0045_permissions_decoupage_roles"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="affectationprojet",
            name="uq_affectation_un_chef_chantier",
        ),
    ]
