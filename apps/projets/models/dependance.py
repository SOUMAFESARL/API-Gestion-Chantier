"""Dépendances entre tâches (décisions v1.2, §13quinquies.5 ; amendement 25/11/2026 ; entreprise).

Quatre types de lien :
- `FS` (défaut) : Fin → Début (B commence après la fin de A)
- `SS` : Début → Début (B commence au plus tôt avec le début de A)
- `FF` : Fin → Fin (B finit au plus tôt avec la fin de A)
- `SF` : Début → Fin (B finit au plus tôt avec le début de A)

Chaque lien porte un décalage signé en jours ouvrés (`decalage_jours`, défaut `0` : positif =
attente / séchage, négatif = avance / chevauchement). Une tâche peut avoir plusieurs prédécesseurs ;
un lien relie deux **feuilles** actives du même projet ; **les boucles sont refusées**.

Retirer un lien est une suppression logique : l'historique des deux tâches le garde.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleEntreprise

__all__ = ["Dependance", "TypeDependance"]


class TypeDependance(models.TextChoices):
    """Types de dépendance planning (compatibles MS Project MSPDI)."""

    FS = "FS", _("Fin → Début (FS)")
    SS = "SS", _("Début → Début (SS)")
    FF = "FF", _("Fin → Fin (FF)")
    SF = "SF", _("Début → Fin (SF)")


class Dependance(ModeleEntreprise):
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
    type_lien = models.CharField(
        _("type de lien"),
        max_length=2,
        choices=TypeDependance.choices,
        default=TypeDependance.FS,
    )
    decalage_jours = models.IntegerField(
        _("décalage (jours ouvrés)"),
        default=0,
        help_text=_("Positif : attente/séchage ; négatif : avance/chevauchement."),
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
        suffixe = ""
        if self.decalage_jours > 0:
            suffixe = f" +{self.decalage_jours}j"
        elif self.decalage_jours < 0:
            suffixe = f" {self.decalage_jours}j"
        return f"{self.predecesseur} —[{self.type_lien}{suffixe}]→ {self.successeur}"
