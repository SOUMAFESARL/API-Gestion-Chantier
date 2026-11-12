"""Modèles SessionInventaire et LigneInventaire — Inventaire physique et ajustement (SFD F9-6).

Table d'entreprise (`ModeleEntreprise`).
À la validation de la session par le Conducteur de Travaux ou Chef de Projet (CP),
les mouvements d'ajustement INVENTAIRE sont automatiquement générés dans MouvementStock.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

try:
    from apps.core.enums import (
        SourceMouvementStock,
        StatutLigneInventaire,
        StatutSessionInventaire,
        TypeMouvementStock,
    )
except ImportError:
    class StatutSessionInventaire(models.TextChoices):  # type: ignore[no-redef]
        BROUILLON = "BROUILLON", _("Brouillon / En cours")
        VALIDE = "VALIDE", _("Validée par le CP")
        ANNULE = "ANNULE", _("Annulée")

    class StatutLigneInventaire(models.TextChoices):  # type: ignore[no-redef]
        CONFORME = "CONFORME", _("Conforme")
        ECART_ACCEPTABLE = "ECART_ACCEPTABLE", _("Écart acceptable")
        DEPASSEMENT_SEUIL = "DEPASSEMENT_SEUIL", _("Dépassement de seuil")

    class TypeMouvementStock(models.TextChoices):  # type: ignore[no-redef]
        ENTREE = "ENTREE", _("Entrée de stock")
        SORTIE = "SORTIE", _("Sortie de stock")
        TRANSFERT = "TRANSFERT", _("Transfert")
        INVENTAIRE = "INVENTAIRE", _("Ajustement d'inventaire")

    class SourceMouvementStock(models.TextChoices):  # type: ignore[no-redef]
        INVENTAIRE = "INVENTAIRE", _("Session d'inventaire")

from apps.core.models import ModeleEntreprise

__all__ = ["LigneInventaire", "SessionInventaire"]


class SessionInventaire(ModeleEntreprise):
    """Session d'inventaire physique périodique sur chantier (SFD F9-6).

    Le Magasinier ouvre la session pour un lot donné et saisit le stock compté.
    Le CP valide la session : des mouvements d'ajustement INVENTAIRE sont alors créés
    automatiquement dans MouvementStock pour régulariser les écarts.
    """

    reference = models.CharField(
        _("référence session"),
        max_length=50,
        db_index=True,
        help_text=_("Exemple : INV-S22-001."),
    )
    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="sessions_inventaire",
        verbose_name=_("projet / chantier"),
    )
    lot = models.ForeignKey(
        "projets.Element",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="sessions_inventaire",
        verbose_name=_("lot de travaux"),
        help_text=_("Lot de travaux concerné (ex: L-01). Nul si inventaire global chantier."),
    )
    magasinier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="sessions_inventaire_effectuees",
        verbose_name=_("magasinier responsable"),
        help_text=_("Magasinier ayant effectué les comptages physiques."),
    )
    date_inventaire = models.DateField(
        _("date d'inventaire"),
        default=timezone.now,
        help_text=_("Date de réalisation du comptage physique."),
    )
    date_cloture = models.DateTimeField(
        _("date de clôture / validation"),
        null=True,
        blank=True,
        help_text=_("Date et heure de validation par le CP."),
    )
    valideur_cp = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="sessions_inventaire_validees",
        verbose_name=_("valideur (CP)"),
        help_text=_("Chef de projet ayant validé la session et autorisé les ajustements."),
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutSessionInventaire.choices,
        default=StatutSessionInventaire.BROUILLON,
        db_index=True,
    )
    commentaire = models.TextField(
        _("observations générales"),
        blank=True,
        default="",
        help_text=_("Synthèse de la session, anomalies constatées ou conclusions de l'enquête."),
    )
    seuil_alerte_ecart_pct = models.DecimalField(
        _("seuil d'alerte écart (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        help_text=_("Seuil en % (défaut 5%). Au-delà, une alerte est émise vers CT et CP."),
    )
    a_depassement_seuil = models.BooleanField(
        _("comporte des dépassements de seuil"),
        default=False,
        help_text=_("Indique si un article a un écart relatif supérieur au seuil d'alerte."),
    )

    class Meta:
        db_table = "session_inventaire"
        verbose_name = _("session d'inventaire")
        verbose_name_plural = _("sessions d'inventaire")
        ordering = ["-date_inventaire", "-cree_le"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "reference"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_session_inventaire_ref_actif",
            ),
        ]

    def __str__(self) -> str:
        lot_str = f" [{self.lot.libelle}]" if self.lot else ""
        statut_lbl = self.get_statut_display()
        return f"Inventaire {self.reference} — {self.date_inventaire}{lot_str} ({statut_lbl})"

    def calculer_ecarts(self) -> None:
        """Recalcule les écarts de toutes les lignes et met à jour l'indicateur d'alerte."""
        has_depassement = False
        for ligne in self.lignes.filter(supprime_le__isnull=True):
            ligne.calculer_ecart(seuil_alerte_pct=self.seuil_alerte_ecart_pct)
            ligne.save(update_fields=["ecart", "ecart_pourcentage", "statut", "modifie_le"])
            if ligne.statut == StatutLigneInventaire.DEPASSEMENT_SEUIL:
                has_depassement = True

        self.a_depassement_seuil = has_depassement
        self.save(update_fields=["a_depassement_seuil", "modifie_le"])

    def valider_et_cloturer(self, valideur, commentaire: str = "") -> list:
        """Valide l'inventaire et génère les mouvements d'ajustement (SFD F9-6, RG-STK-05)."""
        from apps.stock.models.mouvement_stock import MouvementStock

        if self.statut != StatutSessionInventaire.BROUILLON:
            raise ValidationError(
                _("Seule une session d'inventaire au statut BROUILLON peut être validée.")
            )

        now = timezone.now()
        mouvements_crees = []

        with transaction.atomic():
            self.calculer_ecarts()
            self.statut = StatutSessionInventaire.VALIDE
            self.valideur_cp = valideur
            self.date_cloture = now
            if commentaire:
                self.commentaire = f"{self.commentaire}\n{commentaire}".strip()
            self.save(
                update_fields=[
                    "statut",
                    "valideur_cp",
                    "date_cloture",
                    "commentaire",
                    "modifie_le",
                ]
            )

            for ligne in self.lignes.filter(supprime_le__isnull=True):
                if ligne.ecart != Decimal("0.000"):
                    motif = (
                        f"Ajustement inventaire {self.reference} "
                        f"({ligne.article.code} : écart {ligne.ecart:+.3f} "
                        f"{ligne.article.unite_mesure})"
                    )
                    if ligne.commentaire:
                        motif += f" — {ligne.commentaire}"

                    mouvement = MouvementStock(
                        entreprise=self.entreprise,
                        projet=self.projet,
                        lot=self.lot,
                        article=ligne.article,
                        type_mouvement=TypeMouvementStock.INVENTAIRE,
                        quantite=ligne.ecart,
                        source=SourceMouvementStock.INVENTAIRE,
                        reference_piece=self.reference,
                        auteur=valideur,
                        date_mouvement=now,
                        motif=motif,
                    )
                    mouvement.save()
                    mouvements_crees.append(mouvement)

        return mouvements_crees


class LigneInventaire(ModeleEntreprise):
    """Ligne de comptage d'un matériau ou équipement lors d'un inventaire (SFD F9-6)."""

    session_inventaire = models.ForeignKey(
        SessionInventaire,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("session d'inventaire"),
    )
    article = models.ForeignKey(
        "stock.ArticleCatalogue",
        on_delete=models.PROTECT,
        related_name="lignes_inventaire",
        verbose_name=_("article / matériau"),
    )
    stock_theorique = models.DecimalField(
        _("stock théorique"),
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text=_("Stock calculé d'après les mouvements cumulés au lancement."),
    )
    stock_compte = models.DecimalField(
        _("stock compté"),
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text=_("Quantité physiquement dénombrée sur le chantier."),
    )
    ecart = models.DecimalField(
        _("écart constaté"),
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text=_("Stock compté - Stock théorique."),
    )
    ecart_pourcentage = models.DecimalField(
        _("écart relatif (%)"),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Écart en pourcentage relatif par rapport au stock théorique."),
    )
    statut = models.CharField(
        _("statut de l'écart"),
        max_length=25,
        choices=StatutLigneInventaire.choices,
        default=StatutLigneInventaire.CONFORME,
        help_text=_("CONFORME, ECART_ACCEPTABLE ou DEPASSEMENT_SEUIL (> 5%)."),
    )
    commentaire = models.TextField(
        _("justification / enquête"),
        blank=True,
        default="",
        help_text=_("Explication de l'écart (ex: perte coulage, casse, vol)."),
    )

    class Meta:
        db_table = "ligne_inventaire"
        verbose_name = _("ligne d'inventaire")
        verbose_name_plural = _("lignes d'inventaire")
        ordering = ["article__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "session_inventaire", "article"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_ligne_inventaire_session_article",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.article.code} : théorique {self.stock_theorique} / "
            f"compté {self.stock_compte} (écart {self.ecart:+.3f})"
        )

    def calculer_ecart(self, seuil_alerte_pct: Decimal = Decimal("5.00")) -> None:
        """Calcule l'écart absolu et relatif, et qualifie le statut de conformité."""
        self.ecart = self.stock_compte - self.stock_theorique

        if self.stock_theorique != Decimal("0.000"):
            self.ecart_pourcentage = round(
                (self.ecart / abs(self.stock_theorique)) * Decimal("100.00"), 2
            )
        else:
            self.ecart_pourcentage = (
                Decimal("0.00") if self.ecart == Decimal("0.000") else Decimal("100.00")
            )

        if abs(self.ecart_pourcentage or Decimal("0.00")) > seuil_alerte_pct:
            self.statut = StatutLigneInventaire.DEPASSEMENT_SEUIL
        elif self.ecart != Decimal("0.000"):
            self.statut = StatutLigneInventaire.ECART_ACCEPTABLE
        else:
            self.statut = StatutLigneInventaire.CONFORME

    def save(self, *args, **kwargs):
        # Calcul automatique de l'écart à l'enregistrement
        seuil = (
            self.session_inventaire.seuil_alerte_ecart_pct
            if self.session_inventaire_id
            else Decimal("5.00")
        )
        self.calculer_ecart(seuil_alerte_pct=seuil)
        super().save(*args, **kwargs)
