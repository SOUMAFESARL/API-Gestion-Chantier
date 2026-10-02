"""Modèle Activite — MLD §6.3.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets) & 2 (Suivi Technique des Travaux).
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import StatutActivite, UniteMesure
from apps.core.models import ModeleBase

from .lot import Lot

__all__ = ["Activite"]


class Activite(ModeleBase):
    """Activité / Tâche élémentaire de travaux rattachée à un Lot unique."""

    lot = models.ForeignKey(
        Lot,
        on_delete=models.CASCADE,
        related_name="activites",
        verbose_name=_("lot"),
    )
    libelle = models.CharField(
        _("libellé"),
        max_length=200,
    )
    unite = models.CharField(
        _("unité de mesure"),
        max_length=10,
        choices=UniteMesure.choices,
        default=UniteMesure.UNITE,
    )
    quantite_prevue = models.DecimalField(
        _("quantité prévue"),
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    quantite_realisee = models.DecimalField(
        _("quantité réalisée"),
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0.000"))],
    )
    avancement = models.DecimalField(
        _("avancement (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    poids = models.DecimalField(
        _("poids / pondération"),
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_("Pondération dans l'avancement du lot ; par défaut la quantité."),
    )
    date_debut_prevue = models.DateField(
        _("date de début prévue"),
    )
    date_fin_prevue = models.DateField(
        _("date de fin prévue"),
    )
    date_debut_baseline = models.DateField(
        _("date de début baseline v0"),
        null=True,
        blank=True,
        help_text=_("Date de début contractuelle initiale (figée, intacte)."),
    )
    date_fin_baseline = models.DateField(
        _("date de fin baseline v0"),
        null=True,
        blank=True,
        help_text=_("Date de fin contractuelle initiale (figée, intacte)."),
    )
    ordre = models.IntegerField(
        _("ordre"),
        default=1,
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutActivite.choices,
        default=StatutActivite.PLANIFIE,
        db_index=True,
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
    )

    class Meta:
        db_table = "activite"
        verbose_name = _("activité")
        verbose_name_plural = _("activités")
        ordering = ["lot", "ordre", "cree_le"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(date_fin_prevue__gte=models.F("date_debut_prevue")),
                name="chk_activite_dates_coherentes",
            ),
            models.CheckConstraint(
                check=~models.Q(unite="FORFAIT") | models.Q(quantite_prevue=Decimal("1.000")),
                name="chk_activite_forfait",
            ),
        ]

    @property
    def projet(self):
        return self.lot.projet if self.lot_id else None

    @property
    def projet_id(self):
        return self.lot.projet_id if self.lot_id else None

    def save(self, *args, **kwargs):
        """Initialise la Baseline v0 à la première sauvegarde si non définie."""
        if self.date_debut_baseline is None and self.date_debut_prevue:
            self.date_debut_baseline = self.date_debut_prevue
        if self.date_fin_baseline is None and self.date_fin_prevue:
            self.date_fin_baseline = self.date_fin_prevue
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.lot.code} - {self.libelle}"
