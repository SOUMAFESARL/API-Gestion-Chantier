"""Répare les comptes activés avec le prénom recopié dans le nom (« Awa » / « Awa Traoré »).

L'activation écrivait le nom complet de l'invitation dans `nom` : on retire le préfixe
« prénom + espace » quand il y est exactement. Correctif du service : même commit.
"""

from django.db import migrations


def reparer(apps, schema_editor):
    Utilisateur = apps.get_model("accounts", "Utilisateur")
    for utilisateur in Utilisateur.objects.exclude(prenom="").only("id", "prenom", "nom"):
        prefixe = f"{utilisateur.prenom.strip()} "
        if utilisateur.nom.startswith(prefixe) and len(utilisateur.nom) > len(prefixe):
            utilisateur.nom = utilisateur.nom[len(prefixe) :].strip()
            utilisateur.save(update_fields=["nom"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0030_suppression_niveaux")]

    operations = [migrations.RunPython(reparer, migrations.RunPython.noop)]
