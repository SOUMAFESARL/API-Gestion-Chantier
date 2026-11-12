"""Modèle BonCommande — Émission de commande et engagement fournisseur (SFD F9-3).

Table d'entreprise (`ModeleEntreprise`).
Règles clés :
- Émis exclusivement par le DO ou le DG (RG-STK-03).
- Un BC par livraison attendue (SFD §4.2).
- Deux origines possibles : issu d'une DA (`STANDARD`) ou sans DA (`COMMANDE_DIRECTE`, RG-STK-06).
- Clôture manuelle d'un BC partiel par le CP ou le Magasinier (RG-STK-07) avec motif obligatoire
  et génération automatique d'une DA résiduelle pour le reliquat.
- Annulation possible par DO ou DG avant toute réception (motif obligatoire).
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import StatutBonCommande, TypeCommande
from apps.core.fields import QuantiteField
from apps.core.models import ModeleEntreprise

__all__ = [
    "BonCommande",
    "BonDeCommande",
    "LigneBonCommande",
    "LigneBonDeCommande",
]


class BonCommande(ModeleEntreprise):
    """Bon de commande émis pour engagement auprès d'un fournisseur (F9-3).

    Porte l'émetteur (strictement restreint à DO/DG par permission RBAC `stock.bc_emettre`),
    le fournisseur, le chantier/lot de destination, et le lien éventuel vers la DA d'origine.
    """

    reference = models.CharField(
        _("référence"),
        max_length=50,
        db_index=True,
        help_text=_("Identifiant unique du bon de commande (ex: BC-2025-031)."),
    )
    demande_appro = models.ForeignKey(
        "stock.DemandeApprovisionnement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bons_commande",
        verbose_name=_("demande d'approvisionnement source"),
        help_text=_("DA d'origine (nulle si commande directe d'urgence, RG-STK-06)."),
    )
    origine = models.CharField(
        _("origine de commande"),
        max_length=30,
        choices=TypeCommande.choices,
        default=TypeCommande.STANDARD,
        db_index=True,
        help_text=_("STANDARD (issue d'une DA) ou COMMANDE_DIRECTE (urgence direction sans DA)."),
    )
    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="bons_commande",
        verbose_name=_("projet / chantier"),
        help_text=_("Chantier destinataire de la commande."),
    )
    lot = models.ForeignKey(
        "projets.Element",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="bons_commande",
        verbose_name=_("lot de travaux"),
        help_text=_("Lot ou activité de destination (ex: L-01). Nul si global."),
    )
    fournisseur = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="bons_commande_stock",
        verbose_name=_("fournisseur"),
        help_text=_("Tiers avec rôle Fournisseur."),
    )
    emetteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="bons_commande_emis",
        verbose_name=_("émetteur (DO / DG)"),
        help_text=_(
            "Utilisateur habilité ayant émis le BC. Réservé aux rôles DO et DG (RG-STK-03)."
        ),
    )
    date_emission = models.DateField(
        _("date d'émission"),
        default=timezone.now,
        help_text=_("Date de validation et d'émission de la commande."),
    )
    date_livraison_prevue = models.DateField(
        _("date de livraison prévue"),
        null=True,
        blank=True,
        help_text=_("Date attendue sur le chantier."),
    )
    statut = models.CharField(
        _("statut"),
        max_length=30,
        choices=StatutBonCommande.choices,
        default=StatutBonCommande.EMIS,
        db_index=True,
        help_text=_("EMIS, EN_ATTENTE_LIVRAISON, RECU_PARTIELLEMENT, LIVRE, ANNULE."),
    )

    # Clôture manuelle d'un BC partiel (RG-STK-07 : CP ou Magasinier)
    est_cloture_manuellement = models.BooleanField(
        _("clôturé manuellement"),
        default=False,
        help_text=_("Indique si le BC a été clôturé avant livraison complète."),
    )
    date_cloture_manuelle = models.DateTimeField(
        _("date de clôture manuelle"),
        null=True,
        blank=True,
    )
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("clôturé par (CP / Magasinier)"),
    )
    motif_cloture = models.TextField(
        _("motif de clôture manuelle"),
        blank=True,
        default="",
        help_text=_("Motif obligatoire lors de la clôture manuelle d'un BC incomplet (RG-STK-07)."),
    )
    da_residuelle = models.ForeignKey(
        "stock.DemandeApprovisionnement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bc_origines_cloture",
        verbose_name=_("demande approvisionnement résiduelle"),
        help_text=_("DA automatique générée pour le reliquat non livré (RG-STK-07)."),
    )

    # Annulation par DO ou DG avant toute réception (SFD §4.2)
    motif_annulation = models.TextField(
        _("motif d'annulation"),
        blank=True,
        default="",
        help_text=_("Motif obligatoire lors de l'annulation par la direction."),
    )
    date_annulation = models.DateTimeField(
        _("date d'annulation"),
        null=True,
        blank=True,
    )
    annule_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("annulé par"),
    )
    observation = models.TextField(
        _("observation"),
        blank=True,
        default="",
        help_text=_("Conditions de livraison, contact chauffeur ou mentions utiles."),
    )

    class Meta:
        db_table = "stock_bon_commande"
        verbose_name = _("bon de commande")
        verbose_name_plural = _("bons de commande")
        ordering = ["-date_emission", "-cree_le"]
        indexes = [
            models.Index(fields=["entreprise", "statut"]),
            models.Index(fields=["projet", "statut"]),
            models.Index(fields=["fournisseur", "statut"]),
            models.Index(fields=["date_emission"]),
            models.Index(fields=["origine"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "reference"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_stock_bc_reference",
            )
        ]

    def __str__(self) -> str:
        fournisseur_nom = (
            self.fournisseur.nom if self.fournisseur else _("Fournisseur non spécifié")
        )
        return f"{self.reference} · {fournisseur_nom} ({self.get_statut_display()})"

    @property
    def est_direct(self) -> bool:
        """Vérifie s'il s'agit d'une commande directe d'urgence sans DA (RG-STK-06)."""
        return self.origine == TypeCommande.COMMANDE_DIRECTE

    def annuler(self, utilisateur, motif: str):
        """Annule le bon de commande avant réception avec motif obligatoire (SFD §4.2)."""
        if not (motif and motif.strip()):
            raise ValidationError(
                _("Le motif d'annulation est obligatoire pour annuler un BC (SFD §4.2).")
            )
        receptions_validees = self.receptions.filter(
            flag_workflow_valide=True, supprime_le__isnull=True
        ).exists()
        if receptions_validees:
            raise ValidationError(
                _("Impossible d'annuler un BC pour lequel des réceptions ont déjà été validées.")
            )

        self.statut = StatutBonCommande.ANNULE
        self.motif_annulation = motif.strip()
        self.date_annulation = timezone.now()
        self.annule_par = utilisateur
        self.save(
            update_fields=[
                "statut",
                "motif_annulation",
                "date_annulation",
                "annule_par",
                "modifie_le",
            ]
        )

    def cloturer_manuellement(self, utilisateur, motif: str, da_residuelle=None):
        """Clôture manuelle d'un BC partiel par le CP ou le Magasinier (RG-STK-07)."""
        if not (motif and motif.strip()):
            raise ValidationError(
                _("Le motif de clôture manuelle est obligatoire (RG-STK-07).")
            )
        self.est_cloture_manuellement = True
        self.date_cloture_manuelle = timezone.now()
        self.cloture_par = utilisateur
        self.motif_cloture = motif.strip()
        if da_residuelle:
            self.da_residuelle = da_residuelle
        self.save(
            update_fields=[
                "est_cloture_manuellement",
                "date_cloture_manuelle",
                "cloture_par",
                "motif_cloture",
                "da_residuelle",
                "modifie_le",
            ]
        )


class LigneBonCommande(ModeleEntreprise):
    """Ligne d'article associée à un Bon de Commande (SFD F9-3)."""

    bon_commande = models.ForeignKey(
        BonCommande,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("bon de commande"),
    )
    article = models.ForeignKey(
        "stock.ArticleCatalogue",
        on_delete=models.PROTECT,
        related_name="lignes_bon_commande",
        verbose_name=_("article / matériau"),
        help_text=_("Matériau ou équipement commandé."),
    )
    quantite_commandee = QuantiteField(
        _("quantité commandée"),
        help_text=_("Quantité commandée auprès du fournisseur."),
    )
    observation = models.CharField(
        _("observation"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Remarque ou spécification pour cette ligne commandée."),
    )

    class Meta:
        db_table = "stock_ligne_bon_commande"
        verbose_name = _("ligne de bon de commande")
        verbose_name_plural = _("lignes de bon de commande")
        ordering = ["cree_le"]
        indexes = [
            models.Index(fields=["bon_commande", "article"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["bon_commande", "article"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_stock_ligne_bc_article",
            )
        ]

    def __str__(self) -> str:
        unite = self.article.get_unite_mesure_display()
        return (
            f"{self.bon_commande.reference} · {self.article.designation} : "
            f"{self.quantite_commandee} {unite}"
        )

    def clean(self):
        super().clean()
        if self.quantite_commandee is not None and self.quantite_commandee <= Decimal("0"):
            raise ValidationError(
                {"quantite_commandee": _("La quantité commandée doit être strictement positive.")}
            )


# Alias sémantiques conformes SFD / nomenclature
BonDeCommande = BonCommande
LigneBonDeCommande = LigneBonCommande
