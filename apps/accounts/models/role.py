"""Modèles pour la gestion dynamique des rôles et des permissions par module.

Schéma : tenant (et public pour d'éventuels rôles plateforme).
Entités : Role, RoleModulePermission.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.models import ModeleBase

__all__ = ["Role", "RoleModulePermission"]


class Role(ModeleBase):
    """Rôle au sein d'une organisation cliente (tenant).

    Les rôles système (AD, CP, CT, CC, DG, DF, VI) sont initialisés par défaut
    et ne peuvent pas être supprimés pour garantir la stabilité des workflows
    essentiels. Des rôles personnalisés peuvent être créés ou supprimés librement
    par l'administrateur.
    """

    code = models.CharField(_("code"), max_length=50, db_index=True)
    libelle = models.CharField(_("libellé"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    est_systeme = models.BooleanField(
        _("est un rôle système"),
        default=False,
        help_text=_("Un rôle système ne peut pas être supprimé."),
    )
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "role"
        verbose_name = _("rôle")
        verbose_name_plural = _("rôles")
        ordering = ["libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_role_code_actif",
            )
        ]

    def __str__(self) -> str:
        return self.libelle


class RoleModulePermission(ModeleBase):
    """Niveau d'accès d'un rôle sur l'un des 12 modules de CCD Digital.

    Matrice par défaut au niveau de l'entreprise (tenant).
    Niveaux : AUCUN (0), LECTURE (1), ECRITURE (2), VALIDATION (3).
    """

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="permissions_modules",
        verbose_name=_("rôle"),
    )
    module = models.CharField(
        _("module"),
        max_length=30,
        choices=ModuleChoix.choices,
    )
    niveau = models.PositiveSmallIntegerField(
        _("niveau d'accès"),
        choices=NiveauAcces.choices,
        default=NiveauAcces.AUCUN,
    )

    class Meta:
        db_table = "role_module_permission"
        verbose_name = _("permission module du rôle")
        verbose_name_plural = _("permissions modules du rôle")
        constraints = [
            models.UniqueConstraint(
                fields=["role", "module"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_role_module_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.role.libelle} — {self.get_module_display()}: {self.get_niveau_display()}"
