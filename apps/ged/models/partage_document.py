"""Modèle PartageDocument — Lien de partage externe temporaire 72 h (F6 tâche 3.9).

Permet à un profil autorisé (AD, DG, DO ou CP) de générer un lien public sans compte
vers un document du classeur projet, expirant exactement à +72 h et révocable à tout moment.
Table d'entreprise (`ModeleEntreprise` — isolation D9).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleEntreprise

DUREE_PARTAGE_HEURES: int = 72


def generer_jeton_partage() -> str:
    """Génère un jeton aléatoire cryptographiquement sûr (256 bits d'entropie)."""
    return f"tok_{secrets.token_urlsafe(32)}"


def expiration_par_defaut():
    """Échéance réglementaire exacte : maintenant + 72 heures."""
    return timezone.now() + timedelta(hours=DUREE_PARTAGE_HEURES)


class PartageDocument(ModeleEntreprise):
    """Lien temporaire de partage externe rattaché à un document GED."""

    document = models.ForeignKey(
        "ged.Document",
        on_delete=models.CASCADE,
        related_name="partages",
        verbose_name=_("document"),
        db_index=True,
    )
    jeton = models.CharField(
        _("jeton de partage"),
        max_length=64,
        unique=True,
        db_index=True,
        default=generer_jeton_partage,
        help_text=_("Jeton aléatoire de l'URL publique `/partage/<jeton>`."),
    )
    destinataire = models.CharField(
        _("destinataire"),
        max_length=150,
        blank=True,
        default="",
        help_text=_("Nom de l'intervenant ou organisme externe destinataire."),
    )
    note = models.TextField(
        _("note"),
        blank=True,
        default="",
        help_text=_("Contexte ou motif du partage affiché sur la page publique."),
    )
    expire_le = models.DateTimeField(
        _("expire le"),
        default=expiration_par_defaut,
        db_index=True,
        help_text=_("Date et heure exactes d'expiration (+72 h à la création)."),
    )
    revoque = models.BooleanField(
        _("révoqué"),
        default=False,
        db_index=True,
        help_text=_("Indique si le lien a été révoqué manuellement avant son échéance."),
    )
    revoque_le = models.DateTimeField(
        _("révoqué le"),
        null=True,
        blank=True,
    )
    revoque_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("révoqué par"),
    )
    consultations = models.PositiveIntegerField(
        _("nombre de consultations"),
        default=0,
        help_text=_("Compteur de téléchargements effectués via ce lien externe."),
    )

    class Meta:
        db_table = "partage_document"
        verbose_name = _("partage externe de document")
        verbose_name_plural = _("partages externes de documents")
        ordering = ["-cree_le"]
        indexes = [
            models.Index(fields=["document", "-cree_le"], name="idx_partage_doc_date"),
            models.Index(
                fields=["entreprise", "document", "revoque", "expire_le"],
                name="idx_partage_ent_etat",
            ),
        ]

    def __str__(self) -> str:
        return f"Partage {self.document_id} -> {self.destinataire or 'externe'}"

    @property
    def url_publique(self) -> str:
        return f"/partage/{self.jeton}"

    @property
    def est_expire(self) -> bool:
        return self.revoque or timezone.now() >= self.expire_le

    @property
    def est_actif(self) -> bool:
        return not self.est_expire and self.supprime_le is None

    def save(self, *args, **kwargs):
        if not self.entreprise_id and self.document_id:
            self.entreprise_id = self.document.entreprise_id
        if not self.jeton:
            self.jeton = generer_jeton_partage()
        if not self.expire_le:
            self.expire_le = expiration_par_defaut()
        super().save(*args, **kwargs)
