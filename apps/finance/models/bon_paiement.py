"""Modèle BonPaiement et SignatureBon — MLD §6.9.

Schéma : tenant.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ModePaiement, StatutBonPaiement
from apps.core.models import ModeleBase

__all__ = ["BonPaiement", "SignatureBon"]


class BonPaiement(ModeleBase):
    """Bon de paiement pour tâcheron ou sous-traitant."""

    numero = models.CharField(
        _("numéro / référence"),
        max_length=30,
        help_text=_("ex: BDP-2026-001"),
    )
    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="bons_paiement",
        verbose_name=_("projet / chantier"),
    )
    lot = models.ForeignKey(
        "projets.Lot",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="bons_paiement",
        verbose_name=_("lot de travaux"),
    )
    beneficiaire = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        related_name="bons_paiement",
        verbose_name=_("bénéficiaire (tâcheron / sous-traitant)"),
    )
    corps_etat = models.CharField(
        _("corps d'état / prestation"),
        max_length=150,
        blank=True,
        help_text=_("ex: Maçonnerie RDC, Électricité, etc."),
    )
    periode_debut = models.DateField(
        _("période du"),
        default=timezone.now,
    )
    periode_fin = models.DateField(
        _("période au"),
        default=timezone.now,
    )
    montant_brut = models.BigIntegerField(
        _("montant brut (centimes)"),
        default=0,
    )
    deduction_avance = models.BigIntegerField(
        _("déduction avance (centimes)"),
        default=0,
    )
    deduction_penalite = models.BigIntegerField(
        _("déduction pénalité (centimes)"),
        default=0,
    )
    montant_net = models.BigIntegerField(
        _("montant net à payer (centimes)"),
        default=0,
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutBonPaiement.choices,
        default=StatutBonPaiement.A_SIGNER,
    )
    mode_paiement = models.CharField(
        _("mode de paiement"),
        max_length=20,
        choices=ModePaiement.choices,
        default=ModePaiement.VIREMENT,
    )
    reference_paiement = models.CharField(
        _("référence de paiement"),
        max_length=100,
        blank=True,
    )
    paye_le = models.DateTimeField(
        _("payé le"),
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "bon_paiement"
        verbose_name = _("bon de paiement")
        verbose_name_plural = _("bons de paiement")
        ordering = ["-cree_le"]
        indexes = [
            models.Index(fields=["projet", "statut"], name="idx_bdp_proj_statut"),
            models.Index(fields=["statut"], name="idx_bdp_statut"),
        ]

    def save(self, *args, **kwargs):
        if not self.montant_net:
            self.montant_net = max(
                0,
                (self.montant_brut or 0)
                - (self.deduction_avance or 0)
                - (self.deduction_penalite or 0),
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.numero} - {self.beneficiaire} ({self.get_statut_display()})"


class SignatureBon(ModeleBase):
    """Enregistrement d'une signature numérique / validation d'un bon de paiement."""

    bon_paiement = models.ForeignKey(
        BonPaiement,
        on_delete=models.CASCADE,
        related_name="signatures",
        verbose_name=_("bon de paiement"),
    )
    signataire = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.RESTRICT,
        related_name="signatures_bons",
        verbose_name=_("signataire"),
    )
    niveau_requis = models.CharField(
        _("niveau requis"),
        max_length=10,
        default="DG",
    )
    signe_le = models.DateTimeField(
        _("signé le"),
        default=timezone.now,
    )
    commentaire = models.TextField(
        _("commentaire"),
        blank=True,
    )

    class Meta:
        db_table = "signature_bon"
        verbose_name = _("signature de bon")
        verbose_name_plural = _("signatures de bons")
        ordering = ["-signe_le"]

    def __str__(self) -> str:
        return f"Signature {self.bon_paiement.numero} par {self.signataire} le {self.signe_le}"
