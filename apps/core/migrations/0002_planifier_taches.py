"""Les tâches planifiées de la plateforme, inscrites au planificateur (D9, lot 6).

**Le planificateur lit la base, pas les réglages.** `CELERY_BEAT_SCHEDULER` vaut
`django_celery_beat.schedulers:DatabaseScheduler` : une entrée de `settings.CELERY_BEAT_SCHEDULE`
ne serait jamais lue. La planification est une donnée, et elle s'installe par migration pour
qu'aucune base ne l'oublie.

Avant la remise à zéro des migrations, ces quatre entrées vivaient dans `billing` 0003, 0005,
0009 et l'ancienne application des entreprises (0015) ; elles sont réunies ici, en un seul tableau. Les heures sont en UTC, qui
est aussi l'heure d'Abidjan.

- `projets.evaluer_f3_nuit`, 00 h 01 : SFD F3 §4.6 et §7 (rattrapage, santé, statuts, alertes) ;
- `billing.relancer_essais`, 06 h 00 : essai gratuit §2.1, lu à l'ouverture du produit ;
- `billing.relancer_abonnements`, 06 h 00 : rappels d'expiration des abonnements ;
- `billing.verifier_paiements_en_attente`, toutes les 10 min : paiements CinetPay en attente.

Sur cPanel, sans Celery Beat, le cron appelle les commandes équivalentes.
"""

from django.db import migrations

# (nom, tâche, minute, heure)
PLANIFICATION = [
    ("projets.evaluer_f3_nuit", "apps.projets.tasks.evaluer_f3_nuit_toutes_entreprises", "1", "0"),
    ("billing.relancer_essais", "apps.billing.tasks.relancer_essais", "0", "6"),
    ("billing.relancer_abonnements", "apps.billing.tasks.relancer_abonnements", "0", "6"),
    (
        "billing.verifier_paiements_en_attente",
        "apps.billing.tasks.verifier_paiements_en_attente",
        "*/10",
        "*",
    ),
]


def planifier(apps, schema_editor):
    crontab = apps.get_model("django_celery_beat", "CrontabSchedule")
    periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    for nom, tache, minute, heure in PLANIFICATION:
        horaire, _ = crontab.objects.get_or_create(
            minute=minute,
            hour=heure,
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="UTC",
        )
        periodique.objects.update_or_create(
            name=nom,
            defaults={"task": tache, "crontab": horaire, "interval": None, "enabled": True},
        )


def deplanifier(apps, schema_editor):
    periodique = apps.get_model("django_celery_beat", "PeriodicTask")
    periodique.objects.filter(name__in=[nom for nom, *_ in PLANIFICATION]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_isolation_rls"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(planifier, deplanifier)]
