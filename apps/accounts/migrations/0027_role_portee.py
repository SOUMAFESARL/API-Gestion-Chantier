from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0026_utilisateur_role_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="portee",
            field=models.CharField(
                choices=[("ENTREPRISE", "Entreprise"), ("PROJET", "Projet")],
                default="PROJET",
                help_text="Portée d'intervention du rôle : ENTREPRISE (accès global) ou PROJET (accès par affectation).",
                max_length=20,
                verbose_name="portée",
            ),
        ),
    ]
