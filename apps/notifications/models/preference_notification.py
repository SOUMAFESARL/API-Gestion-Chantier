"""Modèle PreferenceNotification — Préférences de notification par collaborateur.

Tables d'entreprise (`ModeleEntreprise`).
Module CDC : Transverse (Socle Commun).
MLD CCD Digital v2.0 §5.5 & Socle Commun §3.1.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import TypeEvenementNotification
from apps.core.models import ModeleEntreprise

__all__ = ["PreferenceNotification"]


class PreferenceNotification(ModeleEntreprise):
    """Préférences de réception des notifications par collaborateur et type d'événement.

    Conforme MLD §5.5 :
    - Détermine pour chaque type d'événement si l'utilisateur souhaite recevoir :
      in-app (cloche), email, push mobile.
    - Contrainte d'unicité `uq_preference` sur (utilisateur, type_evenement).
    """

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="preferences_notification",
        verbose_name=_("utilisateur"),
        db_index=True,
    )
    type_evenement = models.CharField(
        _("type d'événement"),
        max_length=50,
        choices=TypeEvenementNotification.choices,
        db_index=True,
    )
    in_app = models.BooleanField(
        _("in-app"),
        default=True,
        help_text=_("Activer la notification dans la cloche applicative."),
    )
    email = models.BooleanField(
        _("e-mail"),
        default=True,
        help_text=_("Recevoir un e-mail avec bouton d'action directe."),
    )
    push = models.BooleanField(
        _("push mobile"),
        default=False,
        help_text=_("Recevoir une notification push mobile."),
    )

    class Meta:
        db_table = "preference_notification"
        verbose_name = _("préférence de notification")
        verbose_name_plural = _("préférences de notification")
        ordering = ["utilisateur", "type_evenement"]
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "type_evenement"],
                name="uq_preference",
            ),
        ]
        indexes = [
            models.Index(
                fields=["entreprise", "utilisateur"],
                name="idx_pref_notif_ent_usr",
            ),
        ]

    def __str__(self) -> str:
        return f"Préférences de {self.utilisateur} pour {self.type_evenement}"

    @property
    def evenement(self) -> str:
        return self.type_evenement

    @evenement.setter
    def evenement(self, value: str) -> None:
        self.type_evenement = value
