"""Modèle Permission — catalogue dynamique des autorisations granulaires.

Socle IAM / RBAC :
Ce modèle remplace le champ scalaire statique NiveauAcces.
Il permet l'ajout, la modification et la suppression dynamique de permissions
(ex: 'LECTURE', 'ECRITURE', 'VALIDATION', 'SUPPRESSION', etc.) par le Super Admin,
sans hiérarchie imposée (le niveau supérieur n'implique plus les niveaux inférieurs).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["Permission"]


class Permission(ModeleBase):
    """Autorisation granulaire dynamique de la plateforme.

    Chaque enregistrement représente une capacité ou un droit d'action (ex: 'LECTURE', 'ECRITURE').
    Les permissions sont transversales et applicables aux différents modules métier.
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
    modules = models.ManyToManyField(
        "accounts.Module",
        related_name="permissions",
        blank=True,
        verbose_name=_("modules éligibles"),
        help_text=_("Modules fonctionnels et applicatifs autorisés à porter cette permission."),
    )

    class Meta:
        db_table = "permission"
        verbose_name = _("permission")
        verbose_name_plural = _("permissions")
        ordering = ["ordre", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_permission_code_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.code})"
