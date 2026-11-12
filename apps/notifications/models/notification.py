"""Modèle Notification — Notifications in-app, e-mail et push de chantier.

Tables d'entreprise (`ModeleEntreprise`).
Module CDC : Transverse (Socle Commun).
MLD CCD Digital v2.0 §5.5 & Socle Commun §3.1.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CanalNotification, TypeEvenementNotification
from apps.core.models import ModeleEntreprise

__all__ = ["Notification"]


class Notification(ModeleEntreprise):
    """Notification adressée à un utilisateur suite à un événement sur la plateforme ou un chantier.

    Conforme MLD §5.5 :
    - Porte la cloche in-app et mémorise les canaux d'expédition (`canaux_envoyes`).
    - Index partiel sur les non lues (`idx_notif_non_lues`) pour le badge temps réel.
    - Cible du clic : soit `type_objet` / `objet_id`, soit URL directe `url_action`.
    - Mécanisme anti-saturation : `cle_groupe` et `compteur` (ex. 10 photos = 1 notification).
    """

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="notifications",
        verbose_name=_("destinataire"),
        db_index=True,
    )
    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("projet"),
    )
    type_evenement = models.CharField(
        _("type d'événement"),
        max_length=50,
        choices=TypeEvenementNotification.choices,
        db_index=True,
    )
    titre = models.CharField(
        _("titre"),
        max_length=200,
    )
    corps = models.TextField(
        _("corps du message"),
        blank=True,
        default="",
    )

    # Cible du clic / action directe
    type_objet = models.CharField(
        _("type d'objet"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Entité ciblée par l'événement (ex. DOCUMENT, RAPPORT, DA, BC)."),
    )
    objet_id = models.UUIDField(
        _("identifiant de l'objet"),
        null=True,
        blank=True,
        help_text=_("UUID de l'objet métier ciblé."),
    )
    url_action = models.CharField(
        _("URL d'action directe / lien"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Lien direct vers l'écran ou la ressource concernée."),
    )

    # Suivi de lecture
    est_lue = models.BooleanField(
        _("lue"),
        default=False,
        db_index=True,
    )
    lue_le = models.DateTimeField(
        _("lue le"),
        null=True,
        blank=True,
    )

    # Canaux et distribution
    canal = models.CharField(
        _("canal principal"),
        max_length=20,
        choices=CanalNotification.choices,
        default=CanalNotification.IN_APP,
    )
    canaux_envoyes = models.JSONField(
        _("canaux envoyés"),
        default=dict,
        blank=True,
        help_text=_("Détail des canaux utilisés (ex. {'in_app': True, 'email': True})."),
    )

    # Anti-saturation (ex. 10 photos déposées ou 5 alertes similaires regroupées)
    cle_groupe = models.CharField(
        _("clé de regroupement"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Clé d'agrégation d'événements similaires non encore lus."),
    )
    compteur = models.PositiveIntegerField(
        _("compteur de regroupement"),
        default=1,
        help_text=_("Nombre d'occurrences agrégées dans cette notification."),
    )

    class Meta:
        db_table = "notification"
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-cree_le"]
        indexes = [
            # Index partiel MLD §5.5 : badge de cloche temps réel
            models.Index(
                fields=["destinataire"],
                name="idx_notif_non_lues",
                condition=models.Q(est_lue=False),
            ),
            # Recherche chronologique par entreprise et destinataire
            models.Index(
                fields=["entreprise", "destinataire", "-cree_le"],
                name="idx_notif_ent_dest_cree",
            ),
            # Recherche rapide pour regroupement anti-saturation des non lues
            models.Index(
                fields=["destinataire", "cle_groupe", "est_lue"],
                name="idx_notif_dest_grp_lue",
            ),
            # Filtrage chronologique par projet
            models.Index(
                fields=["projet", "-cree_le"],
                name="idx_notif_proj_cree",
            ),
        ]

    def __str__(self) -> str:
        cible = f" [{self.projet.reference}]" if self.projet else ""
        return f"{self.titre}{cible} -> {self.destinataire}"

    # Ergonomie et rétrocompatibilité des accès
    @property
    def evenement(self) -> str:
        return self.type_evenement

    @evenement.setter
    def evenement(self, value: str) -> None:
        self.type_evenement = value

    @property
    def message(self) -> str:
        return self.corps

    @message.setter
    def message(self, value: str) -> None:
        self.corps = value

    @property
    def lien(self) -> str:
        return self.url_action

    @lien.setter
    def lien(self, value: str) -> None:
        self.url_action = value

    @property
    def lue(self) -> bool:
        return self.est_lue

    @lue.setter
    def lue(self, value: bool) -> None:
        self.est_lue = value

    @property
    def date_lecture(self) -> Any:
        return self.lue_le

    @date_lecture.setter
    def date_lecture(self, value: Any) -> None:
        self.lue_le = value

    def marquer_comme_lue(self) -> None:
        """Marque la notification comme lue et horodate la lecture."""
        if not self.est_lue:
            self.est_lue = True
            self.lue_le = timezone.now()
            self.save(update_fields=["est_lue", "lue_le", "modifie_le"])

    def incrementer_regroupement(self, delta: int = 1) -> None:
        """Incrémente le compteur d'anti-saturation lors d'événements répétitifs."""
        self.compteur = (self.compteur or 1) + delta
        self.save(update_fields=["compteur", "modifie_le"])
