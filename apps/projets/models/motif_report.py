"""Modèle MotifReport — motifs dynamiques de report de dates prévisionnelles.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["MotifReport"]


class MotifReport(ModeleBase):
    """Motif dynamique qualifiant la raison d'un report de date prévisionnelle."""

    code = models.CharField(
        _("code"),
        max_length=50,
        help_text=_("Code unique du motif (ex: INTEMPERIES, CLIENT, etc.)."),
    )
    libelle = models.CharField(
        _("libellé"),
        max_length=150,
        help_text=_("Nom lisible affiché aux utilisateurs."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Explications ou conditions d'application de ce motif."),
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
        help_text=_("Désactiver pour masquer dans les formulaires sans briser l'historique."),
    )
    ordre = models.PositiveIntegerField(
        _("ordre d'affichage"),
        default=1,
    )

    class Meta:
        db_table = "motif_report"
        verbose_name = _("motif de report")
        verbose_name_plural = _("motifs de report")
        ordering = ["ordre", "libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_motif_report_code_actif",
            )
        ]

    def __str__(self) -> str:
        return self.libelle
