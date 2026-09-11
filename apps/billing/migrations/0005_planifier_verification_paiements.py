"""Inscrit la vérification automatique des paiements CinetPay au planificateur — toutes les 10 minutes.

Le planificateur lit la base via DatabaseScheduler (django_celery_beat) dans le schéma public.
"""

from django.db import migrations

NOM = "billing.verifier_paiements_en_attente"
TACHE = "apps.billing.tasks.verifier_paiements_en_attente"


def planifier(apps, schema_editor):
    try:
        Crontab = apps.get_model("django_celery_beat", "CrontabSchedule")
        Periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return

    horaire, _ = Crontab.objects.get_or_create(
        minute="*/10",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    Periodique.objects.update_or_create(
        name=NOM,
        defaults={"task": TACHE, "crontab": horaire, "interval": None, "enabled": True},
    )


def deplanifier(apps, schema_editor):
    try:
        Periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return
    Periodique.objects.filter(name=NOM).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_alter_plan_code_facture_paiementabonnement_and_more"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [migrations.RunPython(planifier, deplanifier)]
