"""Surcharge des permissions d'un rôle pour un projet spécifique (Approche Hybride).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.models import ModeleBase

__all__ = ["ProjetRoleModuleOverride"]


class ProjetRoleModuleOverride(ModeleBase):
    """Surcharge du niveau d'accès d'un rôle sur un module pour un chantier précis.

    Si un enregistrement existe pour un triplet (projet, rôle, module), son
    niveau remplace le niveau par défaut de l'entreprise.
    """

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.CASCADE,
        related_name="overrides_permissions",
        verbose_name=_("projet"),
    )
    role = models.ForeignKey(
        "accounts.Role",
        on_delete=models.CASCADE,
        related_name="overrides_projets",
        verbose_name=_("rôle"),
    )
    module = models.CharField(
        _("module"),
        max_length=30,
        choices=ModuleChoix.choices,
    )
    niveau = models.PositiveSmallIntegerField(
        _("niveau d'accès sur ce projet"),
        choices=NiveauAcces.choices,
    )

    class Meta:
        db_table = "projet_role_module_override"
        verbose_name = _("surcharge de permission sur projet")
        verbose_name_plural = _("surcharges de permissions sur projets")
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "role", "module"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_projet_role_module_actif",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.projet.nom} — {self.role.libelle} — "
            f"{self.get_module_display()}: {self.get_niveau_display()}"
        )
