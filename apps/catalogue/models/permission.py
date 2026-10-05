"""Modèle CataloguePermission — autorisations granulaires stockées dans le schéma public."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["CataloguePermission"]


class CataloguePermission(ModeleBase):
    """Autorisation granulaire dynamique de la plateforme.

    Stockée uniquement dans le schéma `public`.
    """

    code = models.CharField(
        _("code"),
        max_length=50,
        db_index=True,
        help_text=_("Code technique unique de l'autorisation (ex: 'LECTURE', 'ECRITURE', 'VALIDATION')."),
    )
    libelle = models.CharField(
        _("libellé"),
        max_length=100,
        help_text=_("Nom officiel et lisible de l'autorisation."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Description de l'action ou capacité conférée par cette permission."),
    )
    ordre = models.PositiveSmallIntegerField(
        _("ordre d'affichage"),
        default=0,
        help_text=_("Position ordonnée dans les grilles et formulaires de permissions."),
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
        help_text=_("Indique si cette permission est active et disponible."),
    )
    reservee_administration = models.BooleanField(
        _("réservée administration"),
        default=False,
        help_text=_("Indique si cette permission est réservée à l'administration de l'entreprise."),
    )
    modules = models.ManyToManyField(
        "catalogue.CatalogueModule",
        related_name="permissions",
        blank=True,
        db_table="catalogue_permission_modules",
        verbose_name=_("modules éligibles"),
        help_text=_("Modules fonctionnels et applicatifs autorisés à porter cette permission."),
    )

    class Meta:
        db_table = "catalogue_permission"
        verbose_name = _("permission catalogue")
        verbose_name_plural = _("permissions catalogue")
        ordering = ["ordre", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_catalogue_permission_code_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.code})"
