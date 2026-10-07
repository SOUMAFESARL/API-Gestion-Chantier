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
    portee = models.CharField(
        _("portée"),
        max_length=20,
        choices=[("ENTREPRISE", "Entreprise"), ("PROJET", "Projet")],
        default="PROJET",
        help_text=_("Portée d'intervention du rôle : ENTREPRISE (accès global) ou PROJET (accès par affectation)."),
    )

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


class RoleModulePermissionQuerySet(models.QuerySet):
    """QuerySet supportant l'alias virtuel 'module_code' pour filtrer par code de module."""

    def filter(self, *args, **kwargs):
        new_args = list(args)
        new_kwargs = {}
        for k, v in kwargs.items():
            if k == "module_code":
                new_args.append(models.Q(module__code__iexact=v) | models.Q(module_catalogue__code__iexact=v))
            elif k.startswith("module_code__"):
                suffix = k[len("module_code__"):]
                new_args.append(models.Q(**{f"module__code__{suffix}": v}) | models.Q(**{f"module_catalogue__code__{suffix}": v}))
            else:
                new_kwargs[k] = v
        return super().filter(*new_args, **new_kwargs)

    def exclude(self, *args, **kwargs):
        new_args = list(args)
        new_kwargs = {}
        for k, v in kwargs.items():
            if k == "module_code":
                new_args.append(models.Q(module__code__iexact=v) | models.Q(module_catalogue__code__iexact=v))
            elif k.startswith("module_code__"):
                suffix = k[len("module_code__"):]
                new_args.append(models.Q(**{f"module__code__{suffix}": v}) | models.Q(**{f"module_catalogue__code__{suffix}": v}))
            else:
                new_kwargs[k] = v
        return super().exclude(*new_args, **new_kwargs)


class RoleModulePermission(ModeleBase):
    """Niveau d'accès d'un rôle sur l'un des modules applicatifs dynamiques BTP.

    Matrice par défaut au niveau de l'entreprise (tenant).
    Niveaux : AUCUN (0), LECTURE (1), ECRITURE (2), VALIDATION (3).
    Intégrité référentielle stricte : la suppression d'un module supprime
    automatiquement en cascade ses habilitations associées.
    """

    objects = RoleModulePermissionQuerySet.as_manager()

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="permissions_modules",
        verbose_name=_("rôle"),
    )
    module = models.ForeignKey(
        "accounts.Module",
        on_delete=models.CASCADE,
        related_name="permissions_roles",
        verbose_name=_("module"),
        null=True,
        blank=True,
    )
    module_catalogue = models.ForeignKey(
        "catalogue.CatalogueModule",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="permissions_roles_catalogue",
        verbose_name=_("module catalogue"),
    )
    permissions_catalogue = models.ManyToManyField(
        "catalogue.CataloguePermission",
        related_name="roles_modules_catalogue",
        blank=True,
        db_table="role_module_permission_permissions_catalogue",
        verbose_name=_("permissions catalogue accordées"),
    )
    niveau = models.PositiveSmallIntegerField(
        _("niveau d'accès"),
        choices=NiveauAcces.choices,
        default=NiveauAcces.AUCUN,
        null=True,
        blank=True,
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
            ),
            models.UniqueConstraint(
                fields=["role", "module_catalogue"],
                condition=models.Q(supprime_le__isnull=True, module_catalogue__isnull=False),
                name="uq_role_module_catalogue_actif",
            ),
        ]

    def __str__(self) -> str:
        mod_libelle = self.module.libelle if self.module_id else "?"
        return f"{self.role.libelle} — {mod_libelle}: {self.get_niveau_display()}"

    @property
    def module_code(self) -> str:
        if self.module_id and self.module:
            return (self.module.code or "").lower()
        if self.module_catalogue_id and self.module_catalogue:
            return (self.module_catalogue.code or "").lower()
        return ""
