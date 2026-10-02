"""Modèle EntrepriseModule — association et droits d'usage par tenant."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["EntrepriseModule"]


class EntrepriseModule(ModeleBase):
    """Droit d'usage d'un module du catalogue par une entreprise (tenant).

    Table stockée dans le schéma `public`, reliant l'entreprise au module du catalogue.
    Permet l'activation/désactivation granulaire par entreprise sans réplication de données.
    """

    entreprise = models.ForeignKey(
        "tenants.Entreprise",
        on_delete=models.CASCADE,
        related_name="modules_souscrits",
        verbose_name=_("entreprise"),
        help_text=_("Entreprise cliente abonnée au module."),
    )
    module = models.ForeignKey(
        "catalogue.CatalogueModule",
        on_delete=models.PROTECT,
        related_name="entreprises_associees",
        verbose_name=_("module"),
        help_text=_("Module catalogue souscrit."),
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
        help_text=_("Indique si le module est actif pour cette entreprise."),
    )

    class Meta:
        db_table = "catalogue_entreprise_module"
        verbose_name = _("module souscrit par l'entreprise")
        verbose_name_plural = _("modules souscrits par les entreprises")
        ordering = ["entreprise", "module__ordre"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "module"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_entreprise_module_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.entreprise.nom} — {self.module.code} ({'actif' if self.est_actif else 'inactif'})"
