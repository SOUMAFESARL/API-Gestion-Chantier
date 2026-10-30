"""Modèle MiseAJourInline — Suivi d'avancement physique manuel (SFD F3 §10).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets) & 2 (Suivi Technique des Travaux).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

from .decoupage import Element

__all__ = ["MiseAJourInline"]


class MiseAJourInline(ModeleBase):
    """Mise à jour manuelle de l'avancement d'une feuille de l'arbre."""

    element = models.ForeignKey(
        Element,
        on_delete=models.RESTRICT,
        related_name="mises_a_jour_inline",
        verbose_name=_("élément"),
        null=True,
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="mises_a_jour_inline_creees",
        verbose_name=_("auteur"),
    )
    quantite_avant = models.DecimalField(
        _("quantité avant"),
        max_digits=14,
        decimal_places=3,
    )
    quantite_apres = models.DecimalField(
        _("quantité après"),
        max_digits=14,
        decimal_places=3,
    )
    avancement_avant = models.DecimalField(
        _("avancement avant (%)"),
        max_digits=5,
        decimal_places=2,
    )
    avancement_apres = models.DecimalField(
        _("avancement après (%)"),
        max_digits=5,
        decimal_places=2,
    )
    commentaire = models.TextField(
        _("commentaire"),
    )
    source = models.CharField(
        _("source"),
        max_length=50,
        default="F3_INLINE",
    )

    class Meta:
        db_table = "mise_a_jour_inline"
        verbose_name = _("mise à jour manuelle d'avancement")
        verbose_name_plural = _("mises à jour manuelles d'avancement")
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        return (
            f"Mise à jour {self.element} : "
            f"{self.quantite_avant} -> {self.quantite_apres} ({self.auteur})"
        )
