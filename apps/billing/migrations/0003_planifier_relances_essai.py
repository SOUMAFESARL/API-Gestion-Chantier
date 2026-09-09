"""Inscrit la relance des essais au planificateur — 06 h 00 UTC.

**Le planificateur lit la base, pas les réglages.** `CELERY_BEAT_SCHEDULER` vaut
`django_celery_beat.schedulers:DatabaseScheduler` : une entrée écrite dans
`settings.CELERY_BEAT_SCHEDULE` ne serait jamais lue. La planification est donc
une donnée, et elle s'installe comme telle — par migration, pour qu'aucun
environnement ne l'oublie.

**06 h 00 UTC** est l'heure retenue par le parcours de l'essai gratuit §2.1,
la même que la tâche de renouvellement : c'est le début de matinée dans les neuf
pays desservis. Le message est lu au moment où l'on ouvre le produit, pas au
milieu de la nuit.
"""

from django.db import migrations

NOM = "billing.relancer_essais"
TACHE = "apps.billing.tasks.relancer_essais"


def planifier(apps, schema_editor):
    try:
        Crontab = apps.get_model("django_celery_beat", "CrontabSchedule")
        Periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        # `django_celery_beat` absent de cet environnement : rien à planifier,
        # et ce n'est pas une raison de faire échouer la migration.
        return

    # Pas de champ `timezone` ici : `apps.get_model` rend le modèle **historique**,
    # et cette colonne n'existait pas encore dans la migration dont nous dépendons.
    # Le planificateur applique `TIME_ZONE`, qui vaut UTC — ce qui est l'heure voulue.
    horaire, _ = Crontab.objects.get_or_create(
        minute="0",
        hour="6",
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
        ("billing", "0002_relanceessai"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [migrations.RunPython(planifier, deplanifier)]
