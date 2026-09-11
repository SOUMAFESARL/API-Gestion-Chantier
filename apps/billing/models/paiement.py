"""Modèle Paiement d'abonnement — MLD §4.5."""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["PaiementAbonnement"]


class PaiementAbonnement(ModeleBase):
    """Règlement d'une facture via CinetPay ou autre moyen — Schéma `public`.

    - `reference_transaction` est UNIQUE : garantie d'idempotence contre les doubles appels webhook.
    - `charge_utile` conserve la réponse brute du prestataire pour audit et résolution des litiges.
    """

    class Mode(models.TextChoices):
        ORANGE_MONEY = "ORANGE_MONEY", _("Orange Money")
        WAVE = "WAVE", _("Wave")
        MTN_MOMO = "MTN_MOMO", _("MTN Mobile Money")
        MOOV_MONEY = "MOOV_MONEY", _("Moov Money")
        CARTE = "CARTE", _("Carte Bancaire (Visa / Mastercard)")
        VIREMENT = "VIREMENT", _("Virement Bancaire")
        AUTRE = "AUTRE", _("Autre")

    class Statut(models.TextChoices):
        INITIE = "INITIE", _("Initié")
        CONFIRME = "CONFIRME", _("Confirmé")
        ECHOUE = "ECHOUE", _("Échoué")
        REMBOURSE = "REMBOURSE", _("Remboursé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    facture = models.ForeignKey(
        "billing.Facture",
        on_delete=models.RESTRICT,
        related_name="paiements",
        verbose_name=_("facture"),
    )

    mode = models.CharField(
        _("mode de paiement"),
        max_length=30,
        choices=Mode.choices,
        default=Mode.AUTRE,
    )

    # Référence interne unique générée par notre système (ex: CMD-20260911-XXXXX)
    reference_commande = models.CharField(
        _("référence commande"),
        max_length=100,
        unique=True,
    )

    # Référence de transaction CinetPay — clé de voûte de l'idempotence
    reference_transaction = models.CharField(
        _("référence transaction"),
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text=_("Identifiant de transaction CinetPay, unique et idempotent"),
    )

    # Montant en centimes de FCFA
    montant = models.BigIntegerField(
        _("montant"),
        help_text=_("Centimes FCFA"),
    )

    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=Statut.choices,
        default=Statut.INITIE,
        db_index=True,
    )

    paye_le = models.DateTimeField(_("payé le"), null=True, blank=True)
    charge_utile = models.JSONField(
        _("charge utile prestataire"),
        default=dict,
        blank=True,
        help_text=_("Réponse brute du prestataire conservée pour litige"),
    )

    class Meta:
        db_table = "paiement_abonnement"
        verbose_name = _("paiement d'abonnement")
        verbose_name_plural = _("paiements d'abonnement")
        ordering = ["-cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(montant__gt=0),
                name="chk_paiement_montant_positif",
            ),
        ]

    def __str__(self) -> str:
        montant = f"{self.montant / 100:,.0f} FCFA"
        mode = self.get_mode_display()
        statut = self.get_statut_display()
        return f"{self.reference_commande} — {mode} ({montant}) [{statut}]"

    @property
    def montant_fcfa(self) -> int:
        return int(self.montant // 100)
