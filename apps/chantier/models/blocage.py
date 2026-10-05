"""Modèle Blocage — Suivi des blocages et points bloquants sur chantier.

Schéma : tenant.
Module CDC : 2 (Suivi Technique et Chantier).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import SeveriteBlocage, StatutBlocage
from apps.core.models import ModeleBase

__all__ = ["Blocage"]


class Blocage(ModeleBase):
    """Point bloquant ou incident survenu sur un chantier."""

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.CASCADE,
        related_name="blocages",
        verbose_name=_("projet"),
    )
    lot = models.ForeignKey(
        "projets.Lot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocages",
        verbose_name=_("lot"),
    )
    titre = models.CharField(
        _("titre"),
        max_length=200,
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
    )
    severite = models.CharField(
        _("sévérité"),
        max_length=20,
        choices=SeveriteBlocage.choices,
        default=SeveriteBlocage.MINEUR,
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutBlocage.choices,
        default=StatutBlocage.OUVERT,
        db_index=True,
    )
    ouvert_le = models.DateTimeField(
        _("ouvert le"),
        default=timezone.now,
    )
    resolu_le = models.DateTimeField(
        _("résolu le"),
        null=True,
        blank=True,
    )
    ouvert_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="blocages_ouverts",
        verbose_name=_("ouvert par"),
    )
    resolu_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="blocages_resolus",
        verbose_name=_("résolu par"),
    )

    class Meta:
        db_table = "blocage"
        verbose_name = _("blocage")
        verbose_name_plural = _("blocages")
        ordering = ["-ouvert_le"]
        indexes = [
            models.Index(fields=["projet", "statut"], name="idx_blocage_projet_statut"),
        ]

    def __str__(self) -> str:
        return f"[{self.get_severite_display()}] {self.titre} ({self.get_statut_display()})"
