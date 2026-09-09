"""Le blocage n'a plus d'échéance — arbitrage Q1 de T-008 §6.3.

`bloque_jusqu_a` portait un horodatage d'expiration : quinze minutes après le
cinquième échec, le compte se rouvrait seul. C'était une **seconde sortie que le
Socle §2.1 ne prévoit pas**, lui qui dit « déblocage par email de
réinitialisation *uniquement* » et le marque obligatoire.

*Conséquence de l'écart : qui cherchait à forcer un compte n'avait aucun besoin
de l'email. Cinq essais, un quart d'heure d'attente, cinq essais de plus —
indéfiniment. L'email n'était qu'une politesse.*

`bloque_le` dit **quand**, non *jusqu'à quand*. Le champ change de sens, pas
seulement de nom : `est_bloque` ne compare plus rien à l'heure courante.

**L'état des comptes bloqués est conservé.** Supprimer la colonne sans la
reporter aurait rouvert, au déploiement, tous les comptes verrouillés à cet
instant — un déblocage de masse silencieux, exactement ce que la règle cherche à
empêcher.
"""

from django.db import migrations, models


def reporter_les_blocages(apps, schema_editor):
    """Un compte dont l'échéance n'est pas passée reste bloqué."""
    from django.utils import timezone

    Utilisateur = apps.get_model("accounts", "Utilisateur")
    maintenant = timezone.now()
    Utilisateur.objects.filter(bloque_jusqu_a__gt=maintenant).update(bloque_le=maintenant)
    # Une échéance déjà passée décrivait un compte redevenu libre : il le reste,
    # `bloque_le` demeure nul.


def rendre_les_echeances(apps, schema_editor):
    """Marche arrière : un compte bloqué retrouve une échéance à quinze minutes."""
    from datetime import timedelta

    from django.utils import timezone

    Utilisateur = apps.get_model("accounts", "Utilisateur")
    Utilisateur.objects.filter(bloque_le__isnull=False).update(
        bloque_jusqu_a=timezone.now() + timedelta(minutes=15)
    )


class Migration(migrations.Migration):

    dependencies = [("accounts", "0007_alter_invitation_role_propose_and_more")]

    operations = [
        migrations.AddField(
            model_name="utilisateur",
            name="bloque_le",
            field=models.DateTimeField(blank=True, null=True, verbose_name="bloqué le"),
        ),
        migrations.RunPython(reporter_les_blocages, rendre_les_echeances),
        migrations.RemoveField(model_name="utilisateur", name="bloque_jusqu_a"),
    ]
