"""Modèle ReceptionChantier — Réception terrain et BRV (SFD F9-4, RG-STK-01, RG-STK-04, RG-STK-13).

Table d'entreprise (`ModeleEntreprise`).
Règles critiques :
- Saisie terrain par le Magasinier (MAG) par rapprochement avec le Bon de Commande (F9-US-08).
- RG-STK-01 : L'entrée effective en stock est conditionnée à DEUX conditions CUMULATIVES :
  1. Validation workflow : CT pour les matériaux, ou circuit séquentiel CT PUIS CP pour
     les équipements (RG-STK-04).
  2. Justificatif physique présent : BL fournisseur signé physiquement, uploadé avec
     empreinte SHA-256 calculée côté serveur (RG-STK-13).
- Tant que l'une des conditions manque, la livraison ne génère AUCUN mouvement d'entrée en stock.
- Génération automatique du numéro BRV séquentiel et archivage dans la GED F6 à la validation.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import StatutReceptionChantier
from apps.core.fields import QuantiteField
from apps.core.models import ModeleEntreprise

__all__ = [
    "BRV",
    "BonReceptionValidation",
    "LigneLivraison",
    "LigneReception",
    "LigneReceptionChantier",
    "Livraison",
    "ReceptionChantier",
]


class ReceptionChantier(ModeleEntreprise):
    """Réception de livraison sur chantier et Bon de Réception et Validation (BRV).

    Matérialise le contrôle physique à l'arrivée du camion par le Magasinier,
    l'instruction technique par la MOE (CT / CP) et la preuve documentaire (BL signé).
    """

    numero_brv = models.CharField(
        _("numéro BRV"),
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Numéro séquentiel auto du BRV (ex: BRV-015), figé à la double validation."),
    )
    bon_commande = models.ForeignKey(
        "stock.BonCommande",
        on_delete=models.RESTRICT,
        related_name="receptions",
        verbose_name=_("bon de commande"),
        help_text=_("BC rattaché à cette livraison."),
    )
    magasinier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="receptions_magasinier",
        verbose_name=_("magasinier"),
        help_text=_("Magasinier ayant effectué la réception physique sur le terrain."),
    )
    date_reception = models.DateField(
        _("date de réception"),
        default=timezone.now,
        help_text=_("Date du déchargement et du contrôle terrain."),
    )
    heure_reception = models.TimeField(
        _("heure de réception"),
        null=True,
        blank=True,
        help_text=_("Heure d'arrivée du camion."),
    )
    statut = models.CharField(
        _("statut"),
        max_length=35,
        choices=StatutReceptionChantier.choices,
        default=StatutReceptionChantier.EN_ATTENTE_VALIDATION_CT,
        db_index=True,
        help_text=_(
            "EN_ATTENTE_VALIDATION_CT, EN_ATTENTE_VALIDATION_CP, VALIDE_WORKFLOW, "
            "VALIDE_AVEC_JUSTIFICATIF, REJETE."
        ),
    )

    # Preuves terrain (max 5 photos, SFD §8)
    photos = models.JSONField(
        _("photos de réception"),
        default=list,
        blank=True,
        help_text=_("Liste des clés ou URL de photos terrain (maximum 5)."),
    )

    # Justificatif physique officiel (BL signé) et empreinte d'intégrité (RG-STK-13)
    fichier_justificatif = models.FileField(
        _("fichier justificatif (BL signé)"),
        upload_to="stock/justificatifs/%Y/%m/",
        null=True,
        blank=True,
        help_text=_("BL papier signé par le magasinier et le livreur, scanné ou photographié."),
    )
    hash_sha256 = models.CharField(
        _("empreinte SHA-256"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("Calculé côté serveur à l'upload pour opposabilité (RG-STK-13)."),
    )

    # Deux flags d'entrée en stock (RG-STK-01)
    flag_workflow_valide = models.BooleanField(
        _("flag validation workflow"),
        default=False,
        help_text=_("Condition 1 : validation CT (matériaux) ou CT puis CP (équipements)."),
    )
    flag_justificatif_present = models.BooleanField(
        _("flag justificatif physique"),
        default=False,
        help_text=_("Condition 2 : BL signé scanné avec SHA-256 présent."),
    )

    # Circuit séquentiel équipements (RG-STK-04)
    est_equipement = models.BooleanField(
        _("contient des équipements"),
        default=False,
        help_text=_(
            "Circuit séquentiel à deux niveaux CT puis CP obligatoire si équipement (RG-STK-04)."
        ),
    )

    # Instruction CT (Conducteur de Travaux)
    valide_par_ct = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("validé par (CT)"),
    )
    date_validation_ct = models.DateTimeField(
        _("date de validation CT"),
        null=True,
        blank=True,
    )
    commentaire_ct = models.TextField(
        _("commentaire technique CT"),
        blank=True,
        default="",
    )

    # Instruction CP (Chef de Projet) — obligatoire si est_equipement ou MOE externe
    valide_par_cp = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("validé par (CP)"),
    )
    date_validation_cp = models.DateTimeField(
        _("date de validation CP"),
        null=True,
        blank=True,
    )
    commentaire_cp = models.TextField(
        _("commentaire CP"),
        blank=True,
        default="",
    )

    # Rejet et bon de retour automatique (SFD §4.3)
    motif_rejet = models.TextField(
        _("motif de rejet"),
        blank=True,
        default="",
        help_text=_("Motif obligatoire si rejet par le CT ou le CP."),
    )
    date_rejet = models.DateTimeField(
        _("date de rejet"),
        null=True,
        blank=True,
    )
    rejete_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("rejeté par"),
    )

    # Connexion GED F6 (SFD §7, F9-US-12)
    document_ged = models.ForeignKey(
        "ged.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receptions_stock",
        verbose_name=_("document GED archivé"),
        help_text=_("Lien vers l'archive F6 du BRV et du BL scanné."),
    )
    observation = models.TextField(
        _("observation"),
        blank=True,
        default="",
        help_text=_("Remarques générales du magasinier lors de la décharge."),
    )

    class Meta:
        db_table = "stock_reception_chantier"
        verbose_name = _("réception de chantier (BRV)")
        verbose_name_plural = _("réceptions de chantier (BRV)")
        ordering = ["-date_reception", "-cree_le"]
        indexes = [
            models.Index(fields=["entreprise", "statut"]),
            models.Index(fields=["bon_commande", "statut"]),
            models.Index(fields=["date_reception"]),
            models.Index(fields=["numero_brv"]),
        ]

    def __str__(self) -> str:
        identifiant = self.numero_brv or f"Réception #{self.id}"
        return f"{identifiant} · {self.bon_commande.reference} ({self.get_statut_display()})"

    @property
    def double_condition_remplie(self) -> bool:
        """Vérifie si les deux conditions cumulatives RG-STK-01 sont satisfaites."""
        return self.flag_workflow_valide and self.flag_justificatif_present

    @property
    def peut_entrer_en_stock(self) -> bool:
        """Indique si le stock effectif peut être incrémenté (RG-STK-01)."""
        return (
            self.statut == StatutReceptionChantier.VALIDE_AVEC_JUSTIFICATIF
            and self.double_condition_remplie
        )

    def clean(self):
        super().clean()
        # RG-STK-04 : Circuit 2 niveaux équipement
        if self.est_equipement and self.valide_par_cp and not self.valide_par_ct:
            raise ValidationError(
                _(
                    "Circuit équipement à 2 niveaux obligatoire (RG-STK-04) : "
                    "la validation CT doit impérativement précéder la validation CP."
                )
            )

        # Limitation photos (maximum 5, SFD §8)
        if self.photos and len(self.photos) > 5:
            raise ValidationError(
                {
                    "photos": _(
                        "Le nombre maximum de photos pour une réception est de 5 (SFD F9 §8)."
                    )
                }
            )

    def recalculer_etats(self):
        """Met à jour les flags d'état et le statut selon les règles F9."""
        # 1. Flag justificatif physique (RG-STK-01 & RG-STK-13)
        self.flag_justificatif_present = bool(self.fichier_justificatif and self.hash_sha256)

        # 2. Flag workflow
        if self.rejete_par_id:
            self.flag_workflow_valide = False
            self.statut = StatutReceptionChantier.REJETE
            return

        if self.est_equipement:
            self.flag_workflow_valide = bool(self.valide_par_ct_id and self.valide_par_cp_id)
        else:
            self.flag_workflow_valide = bool(self.valide_par_ct_id)

        # 3. Statut de livraison résultant
        if self.flag_workflow_valide and self.flag_justificatif_present:
            self.statut = StatutReceptionChantier.VALIDE_AVEC_JUSTIFICATIF
        elif self.flag_workflow_valide and not self.flag_justificatif_present:
            self.statut = StatutReceptionChantier.VALIDE_WORKFLOW
        elif self.est_equipement and self.valide_par_ct_id and not self.valide_par_cp_id:
            self.statut = StatutReceptionChantier.EN_ATTENTE_VALIDATION_CP
        else:
            self.statut = StatutReceptionChantier.EN_ATTENTE_VALIDATION_CT


class LigneReceptionChantier(ModeleEntreprise):
    """Ligne d'article contrôlée lors de la réception terrain (SFD F9-4)."""

    reception = models.ForeignKey(
        ReceptionChantier,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("réception de chantier"),
    )
    ligne_bon_commande = models.ForeignKey(
        "stock.LigneBonCommande",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lignes_reception",
        verbose_name=_("ligne de commande associée"),
        help_text=_("Ligne du BC d'origine pour le rapprochement commandé vs reçu."),
    )
    article = models.ForeignKey(
        "stock.ArticleCatalogue",
        on_delete=models.PROTECT,
        related_name="lignes_reception",
        verbose_name=_("article / matériau"),
        help_text=_("Article livré."),
    )
    quantite_recue = QuantiteField(
        _("quantité reçue"),
        help_text=_("Quantité physique déchargée et constatée par le magasinier."),
    )
    quantite_validee = QuantiteField(
        _("quantité validée"),
        default=Decimal("0.000"),
        help_text=_("Quantité acceptée après contrôle technique par la MOE (CT/CP)."),
    )
    conforme = models.BooleanField(
        _("conforme aux spécifications"),
        default=True,
        help_text=_("Indique si l'article reçu est conforme aux critères de qualité."),
    )
    motif_non_conformite = models.TextField(
        _("motif de non-conformité"),
        blank=True,
        default="",
        help_text=_("Motif obligatoire si l'article est non conforme ou fait l'objet de réserves."),
    )

    class Meta:
        db_table = "stock_ligne_reception_chantier"
        verbose_name = _("ligne de réception de chantier")
        verbose_name_plural = _("lignes de réception de chantier")
        ordering = ["cree_le"]
        indexes = [
            models.Index(fields=["reception", "article"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["reception", "article"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_stock_ligne_reception_article",
            )
        ]

    def __str__(self) -> str:
        unite = self.article.get_unite_mesure_display()
        return (
            f"{self.reception.bon_commande.reference} · {self.article.designation} : "
            f"reçu {self.quantite_recue}, validé {self.quantite_validee} {unite}"
        )

    def clean(self):
        super().clean()
        if self.quantite_recue is not None and self.quantite_recue < Decimal("0"):
            raise ValidationError(
                {"quantite_recue": _("La quantité reçue ne peut pas être négative.")}
            )
        if self.quantite_validee is not None and self.quantite_validee < Decimal("0"):
            raise ValidationError(
                {"quantite_validee": _("La quantité validée ne peut pas être négative.")}
            )
        if not self.conforme and not (
            self.motif_non_conformite and self.motif_non_conformite.strip()
        ):
            raise ValidationError(
                {
                    "motif_non_conformite": _(
                        "Le motif de non-conformité est obligatoire si l'article est non conforme."
                    )
                }
            )


# Alias sémantiques conformes SFD / nomenclature
Livraison = ReceptionChantier
BRV = ReceptionChantier
BonReceptionValidation = ReceptionChantier
LigneLivraison = LigneReceptionChantier
LigneReception = LigneReceptionChantier
