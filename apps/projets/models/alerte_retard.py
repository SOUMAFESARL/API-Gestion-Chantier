"""Modèle AlerteRetard — Alertes de retard et criticité du suivi d'avancement.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets) / F3 (Suivi d'Avancement).
SFD F3 v1.0 §5.4, §10 & Erratum v1.0.1 (E-3).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["AlerteRetard", "NiveauAlerteRetard", "StatutAlerteRetard"]


class NiveauAlerteRetard(models.TextChoices):
    """Niveau de criticité d'une alerte de retard (SFD F3 §5.4)."""

    MODERE = "MODERE", _("Modéré")
    ELEVE = "ELEVE", _("Élevé")
    CRITIQUE = "CRITIQUE", _("Critique")


class StatutAlerteRetard(models.TextChoices):
    """Statut du cycle de vie d'une alerte de retard (SFD F3 §10)."""

    OUVERTE = "OUVERTE", _("Ouverte")
    EN_COURS = "EN_COURS", _("En cours")
    RESOLUE = "RESOLUE", _("Résolue")
    IGNOREE = "IGNOREE", _("Ignorée")


class AlerteRetard(ModeleBase):
    """Alerte de retard détectée automatiquement ou liée à la criticité du projet."""

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="alertes_retard",
        verbose_name=_("projet"),
    )
    lot = models.ForeignKey(
        "projets.Lot",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="alertes_retard",
        verbose_name=_("lot"),
        help_text=_(
            "Lot concerné. Nul pour une alerte de niveau projet "
            "(ex. indice de santé critique)."
        ),
    )
    niveau = models.CharField(
        _("niveau"),
        max_length=10,
        choices=NiveauAlerteRetard.choices,
    )
    delta_pts = models.DecimalField(
        _("delta retard en points"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    indice_sante = models.PositiveSmallIntegerField(
        _("indice de santé"),
        null=True,
        blank=True,
    )
    date_detection = models.DateField(
        _("date de détection"),
    )
    statut = models.CharField(
        _("statut"),
        max_length=10,
        choices=StatutAlerteRetard.choices,
        default=StatutAlerteRetard.OUVERTE,
    )
    causes = models.JSONField(
        _("causes"),
        default=dict,
        blank=True,
    )
    actions_recommandees = models.JSONField(
        _("actions recommandées"),
        default=list,
        blank=True,
    )
    commentaire_resolution = models.TextField(
        _("commentaire de résolution"),
        blank=True,
        default="",
    )
    resolue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes_retard_resolues",
        verbose_name=_("résolue par"),
    )
    resolue_le = models.DateTimeField(
        _("résolue le"),
        null=True,
        blank=True,
    )
    destinataires = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="alertes_retard_recues",
        blank=True,
        verbose_name=_("destinataires"),
    )

    class Meta:
        db_table = "alerte_retard"
        verbose_name = _("alerte de retard")
        verbose_name_plural = _("alertes de retard")
        ordering = ["-date_detection", "-cree_le"]
        indexes = [
            models.Index(fields=["projet", "statut"], name="idx_alerte_retard_proj_stat"),
            models.Index(fields=["lot", "statut"], name="idx_alerte_retard_lot_stat"),
        ]

    def __str__(self) -> str:
        cible = f"lot {self.lot.code}" if self.lot else f"projet {self.projet.reference}"
        return f"Alerte {self.niveau} — {cible} ({self.statut})"
