"""Modèle Facture d'abonnement — MLD §4.5."""

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["Facture"]


class Facture(ModeleBase):
    """Facture émise pour un abonnement SaaS — Schéma `public`.

    Conforme aux règles de facturation OHADA :
    - Numérotation séquentielle continue et sans trou (FAC-AAAA-MM-XXXX).
    - Montants exprimés en centimes de FCFA pour éliminer tout problème d'arrondi.
    - Conserve l'historique complet pour la comptabilité de l'éditeur.
    """

    class Statut(models.TextChoices):
        EMISE = "EMISE", _("Émise")
        PAYEE = "PAYEE", _("Payée")
        IMPAYEE = "IMPAYEE", _("Impayée")
        ANNULEE = "ANNULEE", _("Annulée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    numero = models.CharField(
        _("numéro"),
        max_length=30,
        unique=True,
        help_text=_("Numéro séquentiel conforme OHADA, ex: FAC-2026-09-0001"),
    )

    abonnement = models.ForeignKey(
        "billing.Abonnement",
        on_delete=models.RESTRICT,
        related_name="factures",
        verbose_name=_("abonnement"),
    )
    entreprise = models.ForeignKey(
        "tenants.Entreprise",
        on_delete=models.RESTRICT,
        related_name="factures",
        verbose_name=_("entreprise cliente"),
    )

    periode_debut = models.DateField(_("période début"))
    periode_fin = models.DateField(_("période fin"))

    # Montants en centimes de FCFA (1 FCFA = 100 centimes)
    montant_ht = models.BigIntegerField(_("montant HT (centimes)"))
    taux_tva = models.DecimalField(
        _("taux TVA (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("18.00"),
    )
    montant_tva = models.BigIntegerField(_("montant TVA (centimes)"))
    montant_ttc = models.BigIntegerField(_("montant TTC (centimes)"))

    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=Statut.choices,
        default=Statut.EMISE,
        db_index=True,
    )

    date_emission = models.DateField(_("date d'émission"), default=timezone.localdate)
    date_echeance = models.DateField(_("date d'échéance"))
    fichier_pdf = models.CharField(_("fichier PDF"), max_length=500, blank=True)
    contexte_facturation = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "facture"
        verbose_name = _("facture")
        verbose_name_plural = _("factures")
        ordering = ["-date_emission", "-cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(montant_ht__gte=0),
                name="chk_facture_montant_ht_positif",
            ),
            models.CheckConstraint(
                condition=models.Q(montant_ttc__gte=models.F("montant_ht")),
                name="chk_facture_montant_ttc_gte_ht",
            ),
            models.CheckConstraint(
                condition=models.Q(periode_fin__gte=models.F("periode_debut")),
                name="chk_facture_periodes",
            ),
        ]

    def __str__(self) -> str:
        montant = f"{self.montant_ttc / 100:,.0f} FCFA"
        return f"{self.numero} — {self.entreprise.raison_sociale} ({montant})"

    @property
    def montant_ttc_fcfa(self) -> int:
        """Montant TTC en FCFA bruts (pour envoi vers CinetPay)."""
        return int(self.montant_ttc // 100)

    @classmethod
    def generer_prochain_numero(cls) -> str:
        """Génère un numéro unique OHADA séquentiel sans trou pour le mois en cours."""
        aujourdhui = timezone.localdate()
        prefixe = f"FAC-{aujourdhui.year}-{aujourdhui.month:02d}-"
        derniere = (
            cls.objects.filter(numero__startswith=prefixe)
            .order_by("-numero")
            .values_list("numero", flat=True)
            .first()
        )
        if not derniere:
            sequence = 1
        else:
            try:
                sequence = int(derniere.split("-")[-1]) + 1
            except ValueError:
                sequence = 1
        return f"{prefixe}{sequence:04d}"
