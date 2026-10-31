"""Un rôle peut être « unique par projet » (décision du 30/10/2026).

C'est un réglage de l'entreprise : coché, une seule personne tient le rôle sur un projet. Les
rôles système chef de projet (CP) et chef de chantier (CC) le sont par défaut ; l'entreprise peut
décocher.

**Le `SET CONSTRAINTS ALL IMMEDIATE` en tête est ajouté après coup (31/10/2026).** Quand les
migrations d'un schéma neuf tournent dans une transaction englobante (`get_or_create` d'une
entreprise, `TenantTestCase`), la 0028 a inséré les rôles système quelques migrations plus tôt :
`cree_par` et `supprime_par` sont des clés étrangères à vérification différée, chaque insertion
laisse un déclencheur en attente jusqu'au commit, et PostgreSQL refuse l'`ALTER TABLE role` —
« pending trigger events ». Passer les contraintes en immédiat exécute ces vérifications tout de
suite ; on revient ensuite au différé, comme le fait `check_constraints()` de Django.

Modifier cette migration déjà appliquée est sans risque : Django ne la rejoue pas, l'opération
ajoutée ne change pas l'état des modèles, et seuls les schémas neufs l'exécutent. Une migration
distincte placée avant elle aurait changé ses dépendances — `InconsistentMigrationHistory` sur
chaque tenant existant.
"""

from django.db import migrations, models

UNIQUES_PAR_DEFAUT = ("CP", "CC")


def cocher(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") == "public":
        return
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code__in=UNIQUES_PAR_DEFAUT, supprime_le__isnull=True).update(
        unique_par_projet=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0032_permission_referentiels_ajouter"),
    ]

    operations = [
        migrations.RunSQL(
            "SET CONSTRAINTS ALL IMMEDIATE; SET CONSTRAINTS ALL DEFERRED;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="role",
            name="unique_par_projet",
            field=models.BooleanField(
                default=False,
                help_text="Une seule personne à la fois tient ce rôle sur un projet.",
                verbose_name="unique par projet",
            ),
        ),
        migrations.RunPython(cocher, migrations.RunPython.noop),
    ]
