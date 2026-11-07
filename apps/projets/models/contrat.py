"""Documents contractuels : plusieurs fichiers par projet, de l'entreprise."""

from pathlib import Path

from apps.entreprises.selectors import slug_courant
from django.db import connection, models

from apps.core.models import ModeleEntreprise
from apps.projets.storage import StockageContrats


def chemin_contrat(instance, filename):
    extension = Path(filename).suffix.lower()
    if extension == ".jepg":
        extension = ".jpeg"
    return (
        f"{slug_courant() or 'plateforme'}/projets/{instance.projet_id}/contrats/{instance.pk}{extension}"
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
