"""Modèle SeuilStockLot — Paramétrage des seuils d'alerte de stock par lot (SFD F9, RG-STK-09).

Table d'entreprise (`ModeleEntreprise`).
"""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import QuantiteField
from apps.core.models import ModeleEntreprise

__all__ = ["SeuilStockLot"]


class SeuilStockLot(ModeleEntreprise):
    """Seuil d'alerte de stock défini par lot (ou projet) pour un article donné.

    Initialisé avec la valeur par défaut du référentiel (`ArticleCatalogue.seuil_alerte_defaut`)
    lors du premier approvisionnement sur un lot, puis personnalisable par le Magasinier ou le CP.
    """

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="seuils_stock",
        verbose_name=_("projet / chantier"),
    )
    lot = models.ForeignKey(
        "projets.Element",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="seuils_stock",
        verbose_name=_("lot / élément de découpage"),
        help_text=_("Lot concerné. Nul si le seuil s'applique globalement au projet."),
    )
    article = models.ForeignKey(
        "stock.ArticleCatalogue",
        on_delete=models.PROTECT,
        related_name="seuils_lot",
        verbose_name=_("article du catalogue"),
    )
    seuil_minimum = QuantiteField(
        _("seuil minimum d'alerte"),
        default=Decimal("0.000"),
        help_text=_("Stock sous lequel une alerte est émise vers le CT et le CP."),
    )
    seuil_critique = QuantiteField(
        _("seuil critique / rupture imminente"),
        null=True,
        blank=True,
        help_text=_("Seuil de rupture imminente (alerte rouge)."),
    )
    est_personnalise = models.BooleanField(
        _("est personnalisé"),
        default=False,
        help_text=_("Vrai si le seuil a été modifié par rapport à la valeur par défaut."),
    )
    commentaire = models.CharField(
        _("commentaire"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Motif d'ajustement du seuil."),
    )

    class Meta:
        db_table = "seuil_stock_lot"
        verbose_name = _("seuil de stock par lot")
        verbose_name_plural = _("seuils de stock par lot")
        ordering = ["projet", "lot", "article"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "projet", "lot", "article"],
                condition=models.Q(supprime_le__isnull=True, lot__isnull=False),
                name="uq_seuil_stock_lot_actif",
            ),
            models.UniqueConstraint(
                fields=["entreprise", "projet", "article"],
                condition=models.Q(supprime_le__isnull=True, lot__isnull=True),
                name="uq_seuil_stock_projet_actif",
            ),
        ]

    def __str__(self) -> str:
        lot_str = self.lot.libelle if self.lot else "Tout le projet"
        return f"{self.article.code} @ {lot_str} : seuil min {self.seuil_minimum}"

    def save(self, *args, **kwargs):
        # Initialisation automatique depuis le catalogue si non personnalisé et non renseigné
        if (
            not self.est_personnalise
            and self.seuil_minimum == Decimal("0.000")
            and self.article_id
            and getattr(self.article, "seuil_alerte_defaut", None)
        ):
            self.seuil_minimum = self.article.seuil_alerte_defaut
        super().save(*args, **kwargs)

    def est_en_alerte(self, quantite_stock: Decimal) -> bool:
        """Indique si la quantité en stock est sous le seuil d'alerte."""
        return quantite_stock < self.seuil_minimum

    def est_en_rupture_imminente(self, quantite_stock: Decimal) -> bool:
        """Indique si la quantité en stock a atteint ou franchi le seuil critique."""
        if self.seuil_critique is None:
            return False
        return quantite_stock <= self.seuil_critique
