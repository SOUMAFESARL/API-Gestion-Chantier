"""Les trois variantes du logo, et le passage de l'URL à la clé de stockage.

`logo` contenait une URL toute faite (`/media/logos/demo_1725_x_48.png`). Deux
raisons de ne plus le faire :

* en production le stockage est S3 avec URL signées — une URL persistée y meurt
  au bout de quelques heures ;
* le service produisait déjà un 24 px et un master recadré que rien ne
  référençait. La barre d'application affichait le 48 px dans un emplacement de
  24 px et laissait le navigateur le réduire lui-même.

La migration de données ramène les lignes existantes au format « clé » en
retirant le préfixe `/media/`, et reconstruit les deux nouvelles colonnes par
substitution du suffixe : les fichiers `_24` et `_original` sont sur le disque
depuis le début, ils n'étaient simplement adressés nulle part.
"""

from django.db import migrations, models


def url_vers_cle(apps, schema_editor):
    Entreprise = apps.get_model("tenants", "Entreprise")
    for entreprise in Entreprise.objects.exclude(logo="").iterator():
        cle = entreprise.logo.lstrip("/")
        if cle.startswith("media/"):
            cle = cle[len("media/") :]
        entreprise.logo = cle
        if cle.endswith("_48.png"):
            base = cle[: -len("_48.png")]
            entreprise.logo_24 = f"{base}_24.png"
            entreprise.logo_original = f"{base}_original.png"
        entreprise.save(update_fields=["logo", "logo_24", "logo_original"])


def cle_vers_url(apps, schema_editor):
    Entreprise = apps.get_model("tenants", "Entreprise")
    for entreprise in Entreprise.objects.exclude(logo="").iterator():
        if not entreprise.logo.startswith("/"):
            entreprise.logo = f"/media/{entreprise.logo}"
            entreprise.save(update_fields=["logo"])


class Migration(migrations.Migration):

    dependencies = [("tenants", "0006_entreprise_couleur_primaire")]

    operations = [
        migrations.AddField(
            model_name="entreprise",
            name="logo_24",
            field=models.CharField(blank=True, max_length=500, verbose_name="logo 24 px"),
        ),
        migrations.AddField(
            model_name="entreprise",
            name="logo_original",
            field=models.CharField(blank=True, max_length=500, verbose_name="logo original"),
        ),
        migrations.AlterField(
            model_name="entreprise",
            name="logo",
            field=models.CharField(
                blank=True,
                help_text="Clé de stockage de la vignette 48 px — le rendu par défaut.",
                max_length=500,
                verbose_name="logo",
            ),
        ),
        migrations.RunPython(url_vers_cle, cle_vers_url),
    ]
