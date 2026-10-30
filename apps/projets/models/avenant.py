"""Les avenants au contrat : des jours accordés, un montant, sur le projet ou sur des cases.

Décision du 30/10/2026. Un avenant est enregistré comme **signé**, sans circuit de validation :
c'est le document du client qui fait foi, joint à l'avenant. Il porte sur le projet entier (aucune
case) ou sur des cases précises de l'arbre.

**Trois dates par case** : l'origine (la baseline v0, jamais modifiée), la date **contractuelle**
(l'origine plus les jours accordés par avenant) et la date prévue (le planning, reprogrammé avec
motif). L'alerte au DG mesure la dérive sur la date contractuelle : un délai accordé par le client
n'est plus compté comme un retard.
"""

from pathlib import Path

from django.db import connection, models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase
from apps.projets.storage import StockageContrats

__all__ = ["Avenant"]


def chemin_avenant(instance, filename):
    extension = Path(filename).suffix.lower()
    if extension == ".jepg":
        extension = ".jpeg"
    return (
        f"{connection.schema_name}/projets/{instance.projet_id}/avenants/{instance.pk}{extension}"
    )


class Avenant(ModeleBase):
    projet = models.ForeignKey("projets.Projet", on_delete=models.CASCADE, related_name="avenants")
    numero = models.CharField(_("numéro"), max_length=30)
    date_signature = models.DateField(_("date de signature"))
    objet = models.TextField(_("objet"))
    # Jours calendaires accordés ; négatifs, ils raccourcissent le délai contractuel.
    jours_accordes = models.IntegerField(_("jours accordés"), default=0)
    # En plus ou en moins du budget contractuel, dans l'unité de `Projet.budget_initial_montant`.
    montant = models.BigIntegerField(_("montant"), null=True, blank=True)
    # Aucune case : l'avenant porte sur le projet entier.
    elements = models.ManyToManyField(
        "projets.Element", blank=True, related_name="avenants", db_table="avenant_element"
    )
    document = models.FileField(
        upload_to=chemin_avenant, storage=StockageContrats(), max_length=255, blank=True
    )
    document_nom = models.CharField(max_length=255, blank=True)
    document_type = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "avenant"
        verbose_name = _("avenant")
        verbose_name_plural = _("avenants")
        ordering = ["projet", "date_signature", "cree_le"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "numero"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_avenant_projet_numero",
            )
        ]

    def __str__(self) -> str:
        return f"Avenant {self.numero}"
