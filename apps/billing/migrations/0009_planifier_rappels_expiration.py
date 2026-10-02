from django.db import migrations


def planifier(apps, schema_editor):
    if schema_editor.connection.schema_name != "public":
        return
    crontab_model = apps.get_model("django_celery_beat", "CrontabSchedule")
    periodique_model = apps.get_model("django_celery_beat", "PeriodicTask")
    horaire, _ = crontab_model.objects.get_or_create(
        minute="0",
        hour="6",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    periodique_model.objects.update_or_create(
        name="billing.relancer_abonnements",
        defaults={
            "task": "apps.billing.tasks.relancer_abonnements",
            "crontab": horaire,
            "enabled": True,
        },
    )


def deplanifier(apps, schema_editor):
    if schema_editor.connection.schema_name == "public":
        apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(
            name="billing.relancer_abonnements"
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0008_rappelexpiration"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]
    operations = [migrations.RunPython(planifier, deplanifier)]
