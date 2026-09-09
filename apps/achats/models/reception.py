"""Modèle ReceptionMateriau — Approvisionnements chantier (Module 4).

Schéma : tenant.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["ReceptionMateriau"]


class ReceptionMateriau(ModeleBase):
    """Bon de livraison / Contrôle de réception de matériaux sur chantier."""

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="receptions_materiaux",
        verbose_name=_("projet / chantier"),
    )
    fournisseur = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="receptions_fournisseur",
        verbose_name=_("fournisseur / livreur"),
    )
    designation = models.CharField(
        _("désignation des matériaux"),
        max_length=255,
        help_text=_("ex: 400 sacs ciment CPJ 42.5 livrés & contrôlés"),
    )
    quantite = models.DecimalField(
        _("quantité livrée"),
        max_digits=14,
        decimal_places=3,
        default=1,
    )
    unite = models.CharField(
        _("unité de mesure"),
        max_length=20,
        blank=True,
        default="U",
    )
    conforme = models.BooleanField(
        _("conforme aux spécifications"),
        default=True,
    )
    date_reception = models.DateField(
        _("date de réception"),
        default=timezone.now,
    )
    receptionne_par = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receptions_effectuees",
        verbose_name=_("réceptionné par (magasinier / CT)"),
    )
    observation = models.TextField(
        _("observations / réserves éventuelles"),
        blank=True,
    )

    class Meta:
        db_table = "reception_materiau"
        verbose_name = _("réception de matériau")
        verbose_name_plural = _("réceptions de matériaux")
        ordering = ["-date_reception", "-cree_le"]
        indexes = [
            models.Index(fields=["projet", "date_reception"], name="idx_rec_mat_proj_date"),
        ]

    def __str__(self) -> str:
        statut = "Conforme" if self.conforme else "Non-conforme / Réserves"
        return f"{self.projet.reference} - {self.designation} ({statut})"
