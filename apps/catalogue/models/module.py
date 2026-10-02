"""Modèle CatalogueModule — catalogue partagé dans le schéma public."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["CatalogueModule"]


class CatalogueModule(ModeleBase):
    """Module applicatif dynamique souverain de la plateforme BTP.

    Stocké uniquement dans le schéma `public`. Les tenants y font référence
    directement sans duplication de données ni dérive d'identifiants.
    """

    code = models.CharField(
        _("code"),
        max_length=50,
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
        help_text=_("Indique si le module est actif globalement sur la plateforme."),
    )

    class Meta:
        db_table = "catalogue_module"
        verbose_name = _("module catalogue")
        verbose_name_plural = _("modules catalogue")
        ordering = ["ordre", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_catalogue_module_code_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.code})"
