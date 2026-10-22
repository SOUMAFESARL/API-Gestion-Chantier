"""Inscrit l'évaluation de nuit du suivi d'avancement (F3) au planificateur — 00 h 01 UTC.

**Le planificateur lit la base, pas les réglages.** `CELERY_BEAT_SCHEDULER` vaut
`django_celery_beat.schedulers:DatabaseScheduler` : l'entrée
`evaluation_f3_nuit_tous_tenants` de `settings.CELERY_BEAT_SCHEDULE` n'a donc
jamais été lue, et la tâche de nuit (SFD F3 §4.6 et §7 : rattrapage des
rapports approuvés, indice de santé, statuts, alertes de retard) ne tournait
pas. Même parade que `billing/0003` : la planification s'installe par migration.

**00 h 01 UTC** est l'heure de la SFD ; c'est aussi 00 h 01 à Abidjan (GMT).

Sur cPanel, sans Celery Beat, le cron appelle `manage.py evaluer_f3_nuit` à la
même heure.

Les tables de `django_celery_beat` vivent dans le schéma public : rien à faire
dans un schéma d'entreprise.
"""

from django.db import migrations

NOM = "projets.evaluer_f3_nuit"
TACHE = "apps.projets.tasks.evaluer_f3_nuit_tous_tenants"


def planifier(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    try:
        Crontab = apps.get_model("django_celery_beat", "CrontabSchedule")
        Periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return

    horaire, _ = Crontab.objects.get_or_create(
        minute="1",
        hour="0",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    Periodique.objects.update_or_create(
        name=NOM,
        defaults={"task": TACHE, "crontab": horaire, "interval": None, "enabled": True},
    )


def deplanifier(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    try:
        Periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return
    Periodique.objects.filter(name=NOM).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0014_telephone_entreprise_nom"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [migrations.RunPython(planifier, deplanifier)]
