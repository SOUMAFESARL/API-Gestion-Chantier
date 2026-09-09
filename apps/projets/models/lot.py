"""Modèle Lot — MLD §6.2.

Schéma : tenant.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ModeExecution
from apps.core.models import ModeleBase

from .projet import Projet

__all__ = ["Lot"]


class Lot(ModeleBase):
    """Lot de travaux / Corps d'état rattaché à un projet."""

    projet = models.ForeignKey(
        Projet,
        on_delete=models.RESTRICT,
        related_name="lots",
        verbose_name=_("projet"),
    )
    code = models.CharField(_("code"), max_length=20)
    libelle = models.CharField(_("libellé"), max_length=200)
    phase = models.CharField(_("phase"), max_length=100, blank=True)
    mode_execution = models.CharField(
        _("mode d'exécution"),
        max_length=30,
        choices=ModeExecution.choices,
        default=ModeExecution.REGIE,
    )
    premier_rapport_soumis = models.BooleanField(
        _("premier rapport soumis"),
        default=False,
    )
    ordre = models.IntegerField(_("ordre"), default=1)
    titulaire = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="lots_titulaire",
        verbose_name=_("titulaire / exécutant"),
    )
    date_debut_prevue = models.DateField(
        _("date de début prévue"),
        null=True,
        blank=True,
    )
    date_fin_prevue = models.DateField(
        _("date de fin prévue"),
        null=True,
        blank=True,
    )
    date_debut_reelle = models.DateField(
        _("date de début réelle"),
        null=True,
        blank=True,
    )
    date_fin_reelle = models.DateField(
        _("date de fin réelle"),
        null=True,
        blank=True,
    )
    avancement = models.DecimalField(
        _("avancement (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "lot"
        verbose_name = _("lot")
        verbose_name_plural = _("lots")
        ordering = ["projet", "ordre", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_lot_code",
            )
        ]

    def __str__(self) -> str:
        return f"{self.projet.reference} - {self.code} : {self.libelle}"
