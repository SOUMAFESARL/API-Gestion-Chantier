"""Les dépendances entre tâches (décisions v1.2, §13quinquies.5 ; schéma de l'entreprise).

**Un seul type de lien : B commence après la fin de A**, sans délai. Une tâche peut avoir
plusieurs prédécesseurs ; un lien relie deux **feuilles** du même projet, d'une même branche ou
de deux branches différentes ; **les boucles sont refusées** (`services.dependances`).

Retirer un lien est une suppression logique : l'historique des deux tâches le garde.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["Dependance"]


class Dependance(ModeleBase):
    projet = models.ForeignKey(
        "projets.Projet", on_delete=models.CASCADE, related_name="dependances"
    )
    predecesseur = models.ForeignKey(
        "projets.Element",
        on_delete=models.CASCADE,
        related_name="liens_vers_successeurs",
        verbose_name=_("prédécesseur"),
    )
    successeur = models.ForeignKey(
        "projets.Element",
        on_delete=models.CASCADE,
        related_name="liens_vers_predecesseurs",
        verbose_name=_("successeur"),
    )

    class Meta:
        db_table = "dependance_element"
        verbose_name = _("dépendance entre tâches")
        verbose_name_plural = _("dépendances entre tâches")
        ordering = ["projet", "cree_le"]
        indexes = [models.Index(fields=["projet"], name="idx_dependance_projet")]
        constraints = [
            models.UniqueConstraint(
                fields=["predecesseur", "successeur"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_dependance_lien_actif",
            ),
            models.CheckConstraint(
                condition=~models.Q(predecesseur=models.F("successeur")),
                name="chk_dependance_deux_taches",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.predecesseur} → {self.successeur}"
