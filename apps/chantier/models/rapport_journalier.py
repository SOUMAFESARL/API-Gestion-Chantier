"""Modèle RapportJournalier — MLD §6.7.

Schéma : tenant.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import Meteo, StatutRapport
from apps.core.models import ModeleBase

__all__ = ["RapportJournalier"]


class RapportJournalier(ModeleBase):
    """Journal de chantier quotidien."""

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="rapports_journaliers",
        verbose_name=_("projet / chantier"),
    )
    lot = models.ForeignKey(
        "projets.Lot",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="rapports_journaliers",
        verbose_name=_("lot spécifique"),
    )
    date_rapport = models.DateField(
        _("date du rapport"),
        default=timezone.now,
    )
    auteur = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.RESTRICT,
        related_name="rapports_rediges",
        verbose_name=_("auteur"),
    )
    meteo = models.CharField(
        _("météo"),
        max_length=20,
        choices=Meteo.choices,
        default=Meteo.ENSOLEILLE,
    )
    effectif_regie = models.PositiveSmallIntegerField(
        _("effectif régie"),
        default=0,
    )
    effectif_tacherons = models.PositiveSmallIntegerField(
        _("effectif tâcherons"),
        default=0,
    )
    effectif_present = models.PositiveSmallIntegerField(
        _("effectif total présent"),
        default=0,
    )
    observations = models.TextField(
        _("observations / faits marquants"),
        blank=True,
    )
    blocages_critiques = models.PositiveSmallIntegerField(
        _("nombre de blocages ou incidents critiques"),
        default=0,
    )
    statut = models.CharField(
        _("statut du rapport"),
        max_length=20,
        choices=StatutRapport.choices,
        default=StatutRapport.SOUMIS,
    )
    soumis_le = models.DateTimeField(
        _("soumis le"),
        null=True,
        blank=True,
        default=timezone.now,
    )
    valide_par = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rapports_valides",
        verbose_name=_("validé par (conducteur de travaux)"),
    )
    valide_le = models.DateTimeField(
        _("validé le"),
        null=True,
        blank=True,
    )
    commentaire_validation = models.TextField(
        _("commentaire de validation"),
        blank=True,
    )
    origine = models.CharField(
        _("origine"),
        max_length=10,
        default="WEB",
    )

    class Meta:
        db_table = "rapport_journalier"
        verbose_name = _("rapport journalier")
        verbose_name_plural = _("rapports journaliers")
        ordering = ["-date_rapport", "-cree_le"]
        indexes = [
            models.Index(fields=["projet", "date_rapport"], name="idx_rapport_proj_date"),
            models.Index(fields=["statut"], name="idx_rapport_statut"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["lot", "date_rapport"],
                condition=models.Q(lot__isnull=False),
                name="uq_rapport_lot_date",
            ),
            models.UniqueConstraint(
                fields=["projet", "date_rapport"],
                condition=models.Q(lot__isnull=True),
                name="uq_rapport_projet_date",
            ),
        ]

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        """Un rapport de chantier ne se supprime jamais (MLD §6.7, Socle Commun §3.1)."""
        from apps.core.exceptions import ErreurMetier
        raise ErreurMetier(
            "Un rapport de chantier ne peut pas être supprimé, même logiquement.",
            details={"code": "suppression_interdite"},
        )

    def clean(self):
        super().clean()
        if self.statut == StatutRapport.REJETE:
            if not self.commentaire_validation or len(self.commentaire_validation.strip()) < 20:
                from django.core.exceptions import ValidationError
                raise ValidationError({
                    "commentaire_validation": _(
                        "Le commentaire de rejet doit comporter au moins 20 caractères."
                    )
                })

    def save(self, *args, **kwargs):
        if not self.effectif_present:
            self.effectif_present = (self.effectif_regie or 0) + (self.effectif_tacherons or 0)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        ref = self.projet.reference if self.projet_id else "?"
        return f"Rapport {ref} du {self.date_rapport} ({self.get_statut_display()})"
