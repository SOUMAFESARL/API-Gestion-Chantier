"""Modèle HistoriqueDate — MLD §6.6 & RG-11.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Length
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

from .activite import Activite
from .lot import Lot
from .motif_report import MotifReport
from .projet import Projet

__all__ = ["HistoriqueDate", "TypeObjetHistorique"]


class TypeObjetHistorique(models.TextChoices):
    PROJET = "PROJET", _("Projet")
    LOT = "LOT", _("Lot")
    ACTIVITE = "ACTIVITE", _("Activité")


class HistoriqueDate(ModeleBase):
    """Traçabilité immuable de chaque modification de date prévisionnelle (RG-11)."""

    type_objet = models.CharField(
        _("type d'objet"),
        max_length=20,
        choices=TypeObjetHistorique.choices,
    )
    projet = models.ForeignKey(
        Projet,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="historique_dates",
        verbose_name=_("projet"),
    )
    lot = models.ForeignKey(
        Lot,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="historique_dates",
        verbose_name=_("lot"),
    )
    activite = models.ForeignKey(
        Activite,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="historique_dates",
        verbose_name=_("activité"),
    )
    champ = models.CharField(
        _("champ modifié"),
        max_length=50,
        help_text=_("Nom du champ de date modifié (ex: date_fin_prevue)."),
    )
    valeur_avant = models.DateField(
        _("valeur avant"),
    )
    valeur_apres = models.DateField(
        _("valeur après"),
    )
    motif = models.ForeignKey(
        MotifReport,
        on_delete=models.RESTRICT,
        related_name="historique_dates",
        verbose_name=_("motif de report"),
    )
    justification = models.TextField(
        _("justification"),
        help_text=_("Justification textuelle d'au moins 30 caractères (RG-11)."),
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="modifications_dates",
        verbose_name=_("auteur"),
    )

    class Meta:
        db_table = "historique_date"
        verbose_name = _("historique de date")
        verbose_name_plural = _("historiques de dates")
        ordering = ["-cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(justification__regex=r"^[\s\S]{30,}$"),
                name="chk_historique_date_justification_min_30",
            )
        ]

    def clean(self):
        super().clean()
        if not self.justification or len(self.justification.strip()) < 30:
            raise ValidationError(
                {"justification": _("La justification doit contenir au moins 30 caractères (RG-11).")}
            )
        if not any([self.projet_id, self.lot_id, self.activite_id]):
            raise ValidationError(_("Au moins un objet lié (projet, lot ou activité) doit être renseigné."))

    def __str__(self) -> str:
        cible = self.projet or self.lot or self.activite
        return (
            f"[{self.type_objet}] {cible} — {self.champ} : "
            f"{self.valeur_avant} -> {self.valeur_apres} ({self.motif.libelle})"
        )
