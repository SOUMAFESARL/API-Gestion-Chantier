"""Modèles de l'application tiers — MCD §5.2 et MLD §5.5.

Référentiel unique des acteurs externes (clients, fournisseurs, sous-traitants, tâcherons).
Schéma : tenant.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import RoleTiersChoix, TypeTiers
from apps.core.models import ModeleBase

__all__ = ["RoleTiers", "Tiers"]


class Tiers(ModeleBase):
    """Acteur externe à l'entreprise cliente."""

    type_tiers = models.CharField(
        _("type de tiers"),
        max_length=20,
        choices=TypeTiers.choices,
        default=TypeTiers.ENTREPRISE,
    )
    raison_sociale = models.CharField(_("raison sociale"), max_length=200)
    rccm = models.CharField(_("RCCM"), max_length=50, blank=True)
    nif = models.CharField(_("NIF"), max_length=50, blank=True)
    telephone = models.CharField(_("téléphone"), max_length=20)
    email = models.EmailField(_("email"), blank=True)
    adresse = models.CharField(_("adresse"), max_length=255, blank=True)
    ville = models.CharField(_("ville"), max_length=100, blank=True)
    note_evaluation = models.DecimalField(
        _("note d'évaluation"),
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
    )
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "tiers"
        verbose_name = _("tiers")
        verbose_name_plural = _("tiers")
        ordering = ["raison_sociale"]

    def __str__(self) -> str:
        return self.raison_sociale


class RoleTiers(ModeleBase):
    """Rôle joué par un tiers (un tiers peut être client et sous-traitant)."""

    tiers = models.ForeignKey(Tiers, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(_("rôle"), max_length=30, choices=RoleTiersChoix.choices)

    class Meta:
        db_table = "role_tiers"
        verbose_name = _("rôle de tiers")
        verbose_name_plural = _("rôles de tiers")
        constraints = [
            models.UniqueConstraint(fields=["tiers", "role"], name="uq_role_tiers"),
        ]

    def __str__(self) -> str:
        return f"{self.tiers.raison_sociale} — {self.get_role_display()}"
