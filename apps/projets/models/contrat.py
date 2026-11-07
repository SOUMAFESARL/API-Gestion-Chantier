"""Documents contractuels : plusieurs fichiers par projet, dans le schema tenant."""

from pathlib import Path

from apps.core.passerelle_schema import schema_courant
from django.db import connection, models

from apps.core.models import ModeleEntreprise
from apps.projets.storage import StockageContrats


def chemin_contrat(instance, filename):
    extension = Path(filename).suffix.lower()
    if extension == ".jepg":
        extension = ".jpeg"
    return (
        f"{schema_courant()}/projets/{instance.projet_id}/contrats/{instance.pk}{extension}"
    )


class ProjetContrat(ModeleEntreprise):
    projet = models.ForeignKey("projets.Projet", on_delete=models.CASCADE, related_name="contrats")
    fichier = models.FileField(upload_to=chemin_contrat, storage=StockageContrats(), max_length=255)
    nom = models.CharField(max_length=255)
    taille = models.PositiveBigIntegerField()
    type_contenu = models.CharField(max_length=50)

    class Meta:
        db_table = "projet_contrat"
        ordering = ["cree_le", "id"]
