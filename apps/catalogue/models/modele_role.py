"""Modèles de modèles de rôles (gabarits types) souverains CCD Digital."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import NiveauAcces
from apps.core.models import ModeleBase

__all__ = ["ModeleRole", "ModeleRoleModule"]


class ModeleRole(ModeleBase):
    """Gabarit type de rôle métier BTP souverain.

    Défini au niveau plateforme (schéma public). Sert de matrice de référence
    et de plafond d'habilitation pour les rôles créés ou instanciés dans les tenants.
    """

    code = models.CharField(
        _("code"),
        max_length=50,
        db_index=True,
        help_text=_("Code normalisé du modèle de rôle (ex: DG, AD, DO, DF, CP, CT, CC, MAG, BAI, VI)."),
    )
    libelle = models.CharField(
        _("libellé"),
        max_length=100,
        help_text=_("Nom officiel du modèle de rôle (ex: Conducteur de Travaux)."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Responsabilités et périmètre type du rôle."),
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
        help_text=_("Indique si le modèle est disponible pour les nouvelles entreprises."),
    )

    class Meta:
        db_table = "catalogue_modele_role"
        verbose_name = _("modèle de rôle")
        verbose_name_plural = _("modèles de rôles")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_catalogue_modele_role_code_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.code})"


class ModeleRoleModule(ModeleBase):
    """Plafond d'habilitation d'un modèle de rôle sur un module applicatif.

    Niveau maximum : AUCUN (0), LECTURE (1), ECRITURE (2), VALIDATION (3).
    """

    modele_role = models.ForeignKey(
        ModeleRole,
        on_delete=models.CASCADE,
        related_name="modules_plafonds",
        verbose_name=_("modèle de rôle"),
    )
    module = models.ForeignKey(
        "catalogue.CatalogueModule",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plafonds_modeles_roles",
        verbose_name=_("module catalogue"),
    )
    module_code = models.CharField(
        _("code module"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Code technique du module (ex: 'projets', 'administration')."),
    )
    niveau_max = models.PositiveSmallIntegerField(
        _("niveau d'accès maximum"),
        choices=NiveauAcces.choices,
        default=NiveauAcces.AUCUN,
        help_text=_("Plafond non franchissable par le tenant : 0 Aucun, 1 Lecture, 2 Écriture, 3 Validation."),
    )

    class Meta:
        db_table = "catalogue_modele_role_module"
        verbose_name = _("plafond module du modèle de rôle")
        verbose_name_plural = _("plafonds modules des modèles de rôles")
        ordering = ["modele_role", "module_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["modele_role", "module_code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_modele_role_module_actif",
            )
        ]

    def __str__(self) -> str:
        m_code = self.module_code or (self.module.code if self.module else "?")
        return f"{self.modele_role.code} — {m_code}: max {self.niveau_max}"

    def save(self, *args, **kwargs):
        if self.module and not self.module_code:
            self.module_code = self.module.code.lower()
        if self.module_code:
            self.module_code = self.module_code.lower()
        super().save(*args, **kwargs)
