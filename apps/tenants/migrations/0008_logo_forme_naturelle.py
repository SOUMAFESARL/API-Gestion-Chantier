"""Le logo garde sa forme — 32 px de haut, largeur libre.

Les variantes étaient des **carrés** de 24 et 48 pixels. Un logo d'entreprise
porte presque toujours un nom, souvent une accroche : pressé dans un carré de
24 px, ce texte disparaît, et aucune finesse de réduction n'y change rien.
*Vérifié sur un logo réel — grue, nom et baseline : illisible à 24 px, net à
32 px en forme libre.*

`logo_24` devient `logo_1x` : **le nom ne dit plus la taille.** Il la disait, et
la taille a changé — une colonne qui porte une valeur dans son nom oblige à une
migration à chaque réglage, ou bien elle ment. C'est la leçon de
`bloque_jusqu_a`.

**Les variantes sont régénérées depuis le master déjà stocké.** Le laisser à
Django aurait vidé `logo_1x` et laissé `logo` pointer sur l'ancien carré : la
barre aurait étiré un 48 par 48 sur 32 px de haut, ce qui est pire que l'état
d'avant. Le master recadré est sur le stockage depuis le premier envoi ; il n'y
a donc rien à redemander au client.
"""

import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)


def regenerer_les_variantes(apps, schema_editor):
    """Retaille les deux variantes de barre à partir du master conservé."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    Entreprise = apps.get_model("tenants", "Entreprise")

    for entreprise in Entreprise.objects.exclude(logo_original="").iterator():
        master = entreprise.logo_original
        if not master or not default_storage.exists(master):
            # Plus de master : mieux vaut aucun logo qu'un logo déformé. La
            # barre retombe sur son icône générique, et le client peut
            # téléverser à nouveau quand il le souhaite.
            entreprise.logo = ""
            entreprise.logo_1x = ""
            entreprise.save(update_fields=["logo", "logo_1x"])
            continue

        try:
            import io

            import numpy as np
            from PIL import Image

            from apps.tenants.services.images import (
                HAUTEUR_BARRE,
                prepare_linear,
                reduire_a_hauteur,
                to_pil_rgba,
            )

            with default_storage.open(master) as fichier:
                source = Image.open(io.BytesIO(fichier.read())).convert("RGBA")

            # Le master est **déjà** détouré et recadré : on ne refait que la
            # réduction. Repasser par le détourage risquerait de mordre sur une
            # image qui n'a plus de fond uniforme à retirer.
            stack = prepare_linear(np.asarray(source, dtype=np.float32) / np.float32(255.0))
            racine = master.rsplit("_original", 1)[0]

            for suffixe, hauteur in (("1x", HAUTEUR_BARRE), ("2x", HAUTEUR_BARRE * 2)):
                tampon = io.BytesIO()
                to_pil_rgba(reduire_a_hauteur(stack, hauteur)).save(
                    tampon, format="PNG", optimize=True
                )
                tampon.seek(0)
                cle = f"{racine}_{suffixe}.png"
                if default_storage.exists(cle):
                    default_storage.delete(cle)
                cle = default_storage.save(cle, ContentFile(tampon.read()))
                if suffixe == "1x":
                    entreprise.logo_1x = cle
                else:
                    entreprise.logo = cle

            entreprise.save(update_fields=["logo", "logo_1x"])

        except Exception:
            # Un logo illisible ne doit pas empêcher la migration : elle
            # s'applique schéma par schéma, et un échec ici bloquerait le
            # déploiement entier pour une image.
            logger.exception("Régénération du logo impossible — %s", entreprise.schema_name)
            entreprise.logo = ""
            entreprise.logo_1x = ""
            entreprise.save(update_fields=["logo", "logo_1x"])


def marche_arriere(apps, schema_editor):
    """Rien à défaire : `logo_24` est recréée vide par l'opération inverse."""
    return None


class Migration(migrations.Migration):

    dependencies = [("tenants", "0007_entreprise_logo_variantes")]

    operations = [
        migrations.RenameField(
            model_name="entreprise", old_name="logo_24", new_name="logo_1x"
        ),
        migrations.AlterField(
            model_name="entreprise",
            name="logo_1x",
            field=models.CharField(
                blank=True, max_length=500, verbose_name="logo, densité 1"
            ),
        ),
        migrations.AlterField(
            model_name="entreprise",
            name="logo",
            field=models.CharField(
                blank=True,
                help_text="Clé de stockage de la variante densité 2 — le rendu par défaut.",
                max_length=500,
                verbose_name="logo",
            ),
        ),
        migrations.RunPython(regenerer_les_variantes, marche_arriere),
    ]
