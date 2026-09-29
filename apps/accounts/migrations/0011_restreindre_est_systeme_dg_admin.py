# Migration 0011 — Restreindre est_systeme aux seuls rôles DG et Admin
# Les 6 autres rôles par défaut (CP, CT, CC, MOA, MOE, VI) deviennent
# est_systeme=False afin de permettre leur suppression/modification.

from django.db import migrations


# Codes des seuls rôles qui restent système (non supprimables)
CODES_SYSTEME = {"DG", "AD"}


def restreindre_est_systeme(apps, schema_editor):
    """Passe est_systeme=False sur tous les rôles hors DG et AD."""
    Role = apps.get_model("accounts", "Role")
    Role.objects.exclude(code__in=CODES_SYSTEME).update(est_systeme=False)


def annuler_restriction(apps, schema_editor):
    """Rollback : remet est_systeme=True sur les 8 rôles par défaut."""
    CODES_DEFAUT = {"DG", "AD", "CP", "CT", "CC", "MOA", "MOE", "VI"}
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code__in=CODES_DEFAUT).update(est_systeme=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_alter_invitation_role_propose_and_more"),
    ]

    operations = [
        migrations.RunPython(
            restreindre_est_systeme,
            reverse_code=annuler_restriction,
        ),
    ]
