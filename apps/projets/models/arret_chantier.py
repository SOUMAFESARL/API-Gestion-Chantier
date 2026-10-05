"""Modèle ArretChantier — Périodes d'arrêt ou de suspension de chantier.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["ArretChantier"]


class ArretChantier(ModeleBase):
    """Période d'arrêt de chantier formellement déclarée ou automatique suite à suspension."""

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.CASCADE,
        related_name="arrets_chantier",
        verbose_name=_("projet"),
    )
    date_debut = models.DateField(
        _("date de début"),
    )
    date_fin = models.DateField(
        _("date de fin"),
        null=True,
        blank=True,
        help_text=_("Date de reprise effective ; nulle tant que l'arrêt est en cours."),
    )
    motif = models.TextField(
        _("motif de l'arrêt"),
    )
    declare_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="arrets_declares",
        verbose_name=_("déclaré par"),
    )

    class Meta:
        db_table = "arret_chantier"
        verbose_name = _("arrêt de chantier")
        verbose_name_plural = _("arrêts de chantier")
        ordering = ["-date_debut"]
        constraints = [
            # C7 : Au plus un arrêt ouvert (date_fin nulle) par projet
            models.UniqueConstraint(
                fields=["projet"],
                condition=models.Q(date_fin__isnull=True),
                name="uq_arret_ouvert_par_projet",
            ),
            # C7 : date_fin >= date_debut
            models.CheckConstraint(
                condition=models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=models.F("date_debut")),
                name="chk_arret_date_fin_gte_debut",
            ),
        ]

    def __str__(self) -> str:
        statut_str = f"au {self.date_fin}" if self.date_fin else "en cours"
        return f"Arrêt {self.projet.reference} du {self.date_debut} ({statut_str})"
