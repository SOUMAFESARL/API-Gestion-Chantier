"""Modèle DemandeApprovisionnement — Expression du besoin terrain (SFD F9-2, RG-STK-08).

Table d'entreprise (`ModeleEntreprise`).
Règles clés :
- Émise par le CP ou le Magasinier depuis le smartphone (F9-US-03).
- Modifiable uniquement tant qu'au statut EN_ATTENTE (RG-STK-08).
- Verrouillée dès le premier BC émis (passage à COMMANDEE_PARTIELLEMENT ou COMMANDEE).
- Aucune expiration automatique (SFD §F9-2).
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import StatutDemandeAppro
from apps.core.fields import QuantiteField
from apps.core.models import ModeleEntreprise

__all__ = [
    "DemandeAppro",
    "DemandeApprovisionnement",
    "LigneDemandeAppro",
    "LigneDemandeApprovisionnement",
]


class DemandeApprovisionnement(ModeleEntreprise):
    """Demande d'approvisionnement émise depuis le chantier (F9-2).

    Remplace les échanges informels (WhatsApp, appels) par une saisie structurée
    dans CCD Digital. Elle précise le projet, le lot de travaux, les articles demandés
    avec leurs quantités et la date souhaitée de livraison.
    """

    reference = models.CharField(
        _("référence"),
        max_length=50,
        db_index=True,
        help_text=_("Identifiant unique de la DA (ex: DA-2025-014)."),
    )
    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="demandes_appro",
        verbose_name=_("projet / chantier"),
        help_text=_("Chantier concerné par la demande d'approvisionnement."),
    )
    lot = models.ForeignKey(
        "projets.Element",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="demandes_appro",
        verbose_name=_("lot de travaux"),
        help_text=_("Lot ou activité de destination (ex: L-01 Gros œuvre). Nul si global."),
    )
    emetteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="demandes_appro_emises",
        verbose_name=_("émetteur (demandeur)"),
        help_text=_("Chef de Projet ou Magasinier ayant saisi la DA (F9-US-03)."),
    )
    date_emission = models.DateField(
        _("date d'émission"),
        default=timezone.now,
        help_text=_("Date de soumission de la demande."),
    )
    date_souhaitee = models.DateField(
        _("date souhaitée de livraison"),
        null=True,
        blank=True,
        help_text=_("Date limite souhaitée pour la mise à disposition sur le chantier."),
    )
    observation = models.TextField(
        _("observation"),
        blank=True,
        default="",
        help_text=_("Précisions libres ou contraintes particulières."),
    )
    statut = models.CharField(
        _("statut"),
        max_length=30,
        choices=StatutDemandeAppro.choices,
        default=StatutDemandeAppro.EN_ATTENTE,
        db_index=True,
        help_text=_("EN_ATTENTE, COMMANDEE_PARTIELLEMENT, COMMANDEE, SOLDEE, ANNULEE."),
    )

    # Traçabilité d'annulation par la direction (SFD §4.1)
    motif_annulation = models.TextField(
        _("motif d'annulation"),
        blank=True,
        default="",
        help_text=_("Motif obligatoire si la direction ne donne pas suite."),
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

    class Meta:
        db_table = "stock_demande_approvisionnement"
        verbose_name = _("demande d'approvisionnement")
        verbose_name_plural = _("demandes d'approvisionnement")
        ordering = ["-date_emission", "-cree_le"]
        indexes = [
            models.Index(fields=["entreprise", "statut"]),
            models.Index(fields=["projet", "statut"]),
            models.Index(fields=["date_emission"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "reference"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_stock_da_reference",
            )
        ]

    def __str__(self) -> str:
        return f"{self.reference} · {self.projet.nom} ({self.get_statut_display()})"

    @property
    def demandeur(self):
        """Alias sémantique de l'émetteur (demandeur terrain)."""
        return self.emetteur

    @property
    def est_modifiable(self) -> bool:
        """Vérifie si la DA est modifiable par son émetteur (RG-STK-08)."""
        return self.statut == StatutDemandeAppro.EN_ATTENTE and not self.est_supprime

    def clean(self):
        super().clean()
        # RG-STK-08 : une DA n'est modifiable que si statut == EN_ATTENTE
        if self.pk:
            old = (
                DemandeApprovisionnement.tous_objets.filter(pk=self.pk)
                .values("statut", "projet_id", "lot_id", "date_souhaitee", "observation")
                .first()
            )
            if old and old["statut"] != StatutDemandeAppro.EN_ATTENTE:
                # Si le statut a changé, les transitions sont gérées par le workflow
                # mais le corps de la demande ne peut plus changer.
                champs_modifies = []
                if str(self.projet_id) != str(old["projet_id"]):
                    champs_modifies.append("projet")
                if str(self.lot_id or "") != str(old["lot_id"] or ""):
                    champs_modifies.append("lot")
                if self.date_souhaitee != old["date_souhaitee"]:
                    champs_modifies.append("date_souhaitee")
                if self.observation != old["observation"]:
                    champs_modifies.append("observation")

                if champs_modifies:
                    raise ValidationError(
                        _(
                            "La demande %(ref)s est au statut '%(statut)s' et ne peut plus être "
                            "modifiée (RG-STK-08). Champs verrouillés : %(champs)s."
                        )
                        % {
                            "ref": self.reference,
                            "statut": old["statut"],
                            "champs": ", ".join(champs_modifies),
                        }
                    )

    def annuler(self, utilisateur, motif: str):
        """Annule formellement la DA avec motif obligatoire (SFD §4.1)."""
        if not (motif and motif.strip()):
            raise ValidationError(
                _("Le motif d'annulation est obligatoire pour annuler une DA (SFD §4.1).")
            )
        self.statut = StatutDemandeAppro.ANNULEE
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


class LigneDemandeApprovisionnement(ModeleEntreprise):
    """Ligne d'article associée à une Demande d'Approvisionnement (SFD F9-2)."""

    demande = models.ForeignKey(
        DemandeApprovisionnement,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("demande d'approvisionnement"),
    )
    article = models.ForeignKey(
        "stock.ArticleCatalogue",
        on_delete=models.PROTECT,
        related_name="lignes_demande_appro",
        verbose_name=_("article / matériau"),
        help_text=_("Matériau ou équipement référencé au catalogue."),
    )
    quantite_demandee = QuantiteField(
        _("quantité demandée"),
        help_text=_("Quantité exprimée dans l'unité de mesure de l'article."),
    )
    observation = models.CharField(
        _("observation"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Remarque ou spécification particulière pour cette ligne."),
    )

    class Meta:
        db_table = "stock_ligne_demande_appro"
        verbose_name = _("ligne de demande d'approvisionnement")
        verbose_name_plural = _("lignes de demande d'approvisionnement")
        ordering = ["cree_le"]
        indexes = [
            models.Index(fields=["demande", "article"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["demande", "article"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_stock_ligne_da_article",
            )
        ]

    def __str__(self) -> str:
        unite = self.article.get_unite_mesure_display()
        return (
            f"{self.demande.reference} · {self.article.designation} : "
            f"{self.quantite_demandee} {unite}"
        )

    def clean(self):
        super().clean()
        if self.quantite_demandee is not None and self.quantite_demandee <= Decimal("0"):
            raise ValidationError(
                {"quantite_demandee": _("La quantité demandée doit être strictement positive.")}
            )
        if self.demande_id and not self.demande.est_modifiable:
            raise ValidationError(
                _(
                    "Impossible de modifier les lignes d'une demande verrouillée "
                    "(statut '%(statut)s', RG-STK-08)."
                )
                % {"statut": self.demande.statut}
            )


# Alias sémantiques conformes SFD / nomenclature abrégée
DemandeAppro = DemandeApprovisionnement
LigneDemandeAppro = LigneDemandeApprovisionnement
