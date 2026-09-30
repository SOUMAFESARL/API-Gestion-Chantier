"""Modèle Module — catalogue dynamique des modules applicatifs de CCD Digital.

Socle IAM / RBAC :
Ce modèle remplace l'énumération statique ModuleChoix au niveau de la base de données.
Il permet l'activation, la désactivation et l'ajout dynamique de modules métier,
tout en assurant une intégrité référentielle stricte (CASCADE) sur les habilitations de rôles
et les surcharges par projet.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["Module"]


class Module(ModeleBase):
    """Module applicatif dynamique de la plateforme BTP.

    Chaque enregistrement représente un module fonctionnel activable (ex: projets, chantier, ged...).
    La suppression physique n'existe pas (ModeleBase §3.1) ; la désactivation ou la suppression
    logique d'un module désactive ses permissions associées.
    """

    code = models.CharField(
        _("code"),
        max_length=30,
        db_index=True,
        help_text=_("Code technique unique du module (ex: 'projets', 'chantier', 'ged')."),
    )
    libelle = models.CharField(
        _("libellé"),
        max_length=100,
        help_text=_("Nom officiel et lisible du module."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Périmètre fonctionnel et fonctionnalités couvertes par ce module."),
    )
    ordre = models.PositiveSmallIntegerField(
        _("ordre d'affichage"),
        default=0,
        help_text=_("Position ordonnée dans la navigation et les matrices de permissions."),
    )
    icone = models.CharField(
        _("icône"),
        max_length=50,
        blank=True,
        default="box",
        help_text=_("Identifiant de l'icône Lucide / frontend associée."),
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
        help_text=_("Indique si le module est disponible dans ce tenant."),
    )

    class Meta:
        db_table = "module"
        verbose_name = _("module")
        verbose_name_plural = _("modules")
        ordering = ["ordre", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_module_code_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.code})"
