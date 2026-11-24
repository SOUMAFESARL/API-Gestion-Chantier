"""Documents contractuels : contrat du marché unique actif avec historique de versions."""

from pathlib import Path

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleEntreprise
from apps.entreprises.selectors import slug_courant
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
    nom = models.CharField(_("nom du fichier"), max_length=255)
    taille = models.PositiveBigIntegerField(_("taille (octets)"))
    type_contenu = models.CharField(_("type MIME"), max_length=50)
    version = models.PositiveIntegerField(_("version"), default=1)
    est_actif = models.BooleanField(_("est actif"), default=True, db_index=True)

    class Meta:
        db_table = "projet_contrat"
        ordering = ["-version", "-cree_le", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet"],
                condition=models.Q(est_actif=True, supprime_le__isnull=True),
                name="uq_projet_contrat_unique_actif",
            ),
        ]

    @property
    def nom_sans_extension(self) -> str:
        """Nom du document sans son extension (.pdf, .png, .jpg, etc.)."""
        return Path(self.nom).stem if self.nom else ""

    def __str__(self) -> str:
        etat = "actif" if self.est_actif else "archivé"
        return f"v{self.version} — {self.nom} ({etat})"
