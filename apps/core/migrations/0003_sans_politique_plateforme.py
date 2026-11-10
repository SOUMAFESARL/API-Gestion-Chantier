"""Remplace l'installation des politiques, y compris si elle n'a jamais réussi.

L'ancienne migration reste dans l'historique pour les bases où elle est appliquée.
La migration suivante retire la RLS dans les deux cas.
"""

from django.db import migrations


class Migration(migrations.Migration):
    replaces = [("core", "0003_plateforme_sans_role")]
    dependencies = [("core", "0002_planifier_taches")]
    operations = []
