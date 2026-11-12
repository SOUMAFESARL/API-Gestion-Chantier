"""Modèle MouvementStock — Journal comptable immuable des flux de stock (SFD F9-5, RG-STK-05).

Table d'entreprise (`ModeleEntreprise`).
Règle critique RG-STK-05 : chaque mouvement est strictement IMMUABLE.
Aucune modification (UPDATE) ni suppression (DELETE) n'est autorisée.
Toute correction s'opère par contre-passation (mouvement inverse avec motif obligatoire).
"""

import hashlib
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

try:
    from apps.core.enums import SourceMouvementStock, TypeMouvementStock
except ImportError:
    class TypeMouvementStock(models.TextChoices):  # type: ignore[no-redef]
        ENTREE = "ENTREE", _("Entrée de stock")
        SORTIE = "SORTIE", _("Sortie de stock")
        TRANSFERT = "TRANSFERT", _("Transfert")
        INVENTAIRE = "INVENTAIRE", _("Ajustement d'inventaire")

    class SourceMouvementStock(models.TextChoices):  # type: ignore[no-redef]
        BRV = "BRV", _("Bon de réception et validation")
        F2 = "F2", _("Rapport journalier F2")
        MANUEL = "MANUEL", _("Sortie manuelle")
        INVENTAIRE = "INVENTAIRE", _("Session d'inventaire")
        TRANSFERT = "TRANSFERT", _("Transfert inter-lots / inter-chantiers")

from apps.core.managers import ManagerEntrepriseActif, RequeteEntreprise
from apps.core.models import ModeleEntreprise

__all__ = ["ErreurMouvementImmuable", "MouvementStock"]


class ErreurMouvementImmuable(ValidationError):  # noqa: N818 — nommage français du dépôt
    """Exception levée en cas de tentative de modification ou suppression d'un mouvement."""


class RequeteMouvementStock(RequeteEntreprise):
    """QuerySet assurant l'immutabilité stricte des mouvements de stock."""

    def update(self, **kwargs):
        raise ErreurMouvementImmuable(
            _("Mouvements immuables : mise à jour en masse interdite (RG-STK-05).")
        )

    def delete(self):
        raise ErreurMouvementImmuable(
            _("Les mouvements de stock ne peuvent pas être supprimés (RG-STK-05).")
        )

    def supprimer_logiquement(self, utilisateur=None):
        raise ErreurMouvementImmuable(
            _("Les mouvements ne peuvent pas être supprimés logiquement (RG-STK-05).")
        )


class ManagerMouvementStock(ManagerEntrepriseActif):
    """Manager garantissant le cloisonnement multi-tenant et l'immutabilité des flux."""

    def get_queryset(self):
        return RequeteMouvementStock.cloisonnee(self.model, using=self._db).filter(
            supprime_le__isnull=True
        )


class MouvementStock(ModeleEntreprise):
    """Mouvement de stock immuable (journal comptable des flux de chantier).

    SFD F9-5 & RG-STK-05 :
    - ENTREE : Réception sur chantier après double validation BRV (CT/CP + justificatif).
    - SORTIE : Consommation chantier via signal F2 (rapport CT) ou sortie manuelle justifiée.
    - TRANSFERT : Transfert inter-lots ou inter-chantiers avec justificatif obligatoire.
    - INVENTAIRE : Ajustement d'écart suite à clôture d'inventaire physique par le CP.
    """

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="mouvements_stock",
        verbose_name=_("projet / chantier source"),
        help_text=_("Chantier sur lequel s'applique le mouvement."),
    )
    lot = models.ForeignKey(
        "projets.Element",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="mouvements_stock",
        verbose_name=_("lot de travaux source"),
        help_text=_("Lot de travaux concerné (ex: L-01). Nul si niveau projet global."),
    )
    article = models.ForeignKey(
        "stock.ArticleCatalogue",
        on_delete=models.PROTECT,
        related_name="mouvements_stock",
        verbose_name=_("article / matériau"),
        help_text=_("Matériau ou équipement référencé au catalogue."),
    )
    type_mouvement = models.CharField(
        _("type de mouvement"),
        max_length=20,
        choices=TypeMouvementStock.choices,
        db_index=True,
        help_text=_("ENTREE, SORTIE, TRANSFERT ou INVENTAIRE."),
    )
    quantite = models.DecimalField(
        _("quantité"),
        max_digits=14,
        decimal_places=3,
        help_text=_("Quantité dans l'unité de l'article (positive ou signée pour ajustement)."),
    )
    source = models.CharField(
        _("source du mouvement"),
        max_length=20,
        choices=SourceMouvementStock.choices,
        db_index=True,
        help_text=_("Origine du déclenchement (BRV, F2, MANUEL, INVENTAIRE, TRANSFERT)."),
    )
    reference_piece = models.CharField(
        _("référence de la pièce source"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text=_("N° de BRV, N° de rapport F2, N° de session INV ou N° de transfert."),
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="mouvements_stock_enregistres",
        verbose_name=_("auteur"),
        help_text=_("Utilisateur responsable de l'action ou ayant validé la pièce source."),
    )
    date_mouvement = models.DateTimeField(
        _("date et heure du mouvement"),
        default=timezone.now,
        db_index=True,
        help_text=_("Horodatage effectif du mouvement de matière."),
    )
    motif = models.TextField(
        _("motif / justification"),
        blank=True,
        default="",
        help_text=_("Motif obligatoire pour sorties manuelles, corrections et transferts."),
    )

    # --- Transferts inter-lots ou inter-chantiers (SFD F9-5, RG-STK-10) ---
    projet_destination = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="mouvements_stock_transfert_recus",
        verbose_name=_("projet / chantier destinataire"),
        help_text=_("Renseigné uniquement en cas de transfert inter-chantiers."),
    )
    lot_destination = models.ForeignKey(
        "projets.Element",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="mouvements_stock_transfert_recus",
        verbose_name=_("lot destinataire"),
        help_text=_("Renseigné uniquement en cas de transfert inter-lots."),
    )

    # --- Lien vers mouvement parent / contre-passation (RG-STK-05) ---
    mouvement_parent = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="mouvements_correctifs",
        verbose_name=_("mouvement d'origine"),
        help_text=_("Lien vers le mouvement initial en cas de contre-passation."),
    )

    # --- Justificatif physique signé et empreinte (RG-STK-10, RG-STK-13) ---
    fichier_justificatif = models.FileField(
        _("justificatif signé"),
        upload_to="stock/justificatifs/%Y/%m/",
        null=True,
        blank=True,
        help_text=_("Photo ou scan du bon de transfert signé ou pièce justificative."),
    )
    hash_sha256 = models.CharField(
        _("empreinte SHA-256"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("Garantie d'intégrité calculée à l'enregistrement du document."),
    )

    objects = ManagerMouvementStock()

    class Meta:
        db_table = "mouvement_stock"
        verbose_name = _("mouvement de stock")
        verbose_name_plural = _("mouvements de stock")
        ordering = ["-date_mouvement", "-cree_le"]
        indexes = [
            models.Index(
                fields=["entreprise", "projet", "article", "date_mouvement"],
                name="idx_mvt_stk_prj_art_date",
            ),
            models.Index(fields=["entreprise", "lot", "article"], name="idx_mvt_stk_lot_art"),
            models.Index(fields=["entreprise", "reference_piece"], name="idx_mvt_stk_ref_piece"),
            models.Index(fields=["entreprise", "type_mouvement"], name="idx_mvt_stk_type"),
        ]

    def __str__(self) -> str:
        lot_str = f" [{self.lot.libelle}]" if self.lot else ""
        return (
            f"{self.type_mouvement} {self.quantite:+.3f} {self.article.code} "
            f"@ {self.projet.nom}{lot_str}"
        )

    @property
    def quantite_signee(self) -> Decimal:
        """Retourne la quantité avec son signe comptable algébrique."""
        if self.type_mouvement == TypeMouvementStock.SORTIE:
            return -abs(self.quantite)
        if self.type_mouvement == TypeMouvementStock.ENTREE:
            return abs(self.quantite)
        return self.quantite

    def clean(self):
        super().clean()
        if self.quantite == Decimal("0.000"):
            raise ValidationError(
                {"quantite": _("La quantité d'un mouvement ne peut pas être nulle.")}
            )

        # Règles RG-STK-05 & RG-STK-10
        if (
            self.type_mouvement == TypeMouvementStock.SORTIE
            and self.source == SourceMouvementStock.MANUEL
            and (not self.motif or len(self.motif.strip()) < 10)
        ):
            raise ValidationError(
                {"motif": _("Motif d'au moins 10 caractères requis pour une sortie manuelle.")}
            )

        if self.type_mouvement == TypeMouvementStock.TRANSFERT:
            if not self.motif or len(self.motif.strip()) < 10:
                raise ValidationError(
                    {"motif": _("Un motif d'au moins 10 caractères est requis pour un transfert.")}
                )
            if not self.lot_destination and not self.projet_destination:
                raise ValidationError(
                    _("Un transfert exige un lot ou un chantier de destination.")
                )

        # Calcul automatique du SHA-256 si fichier fourni
        if self.fichier_justificatif and not self.hash_sha256:
            try:
                hasher = hashlib.sha256()
                for chunk in self.fichier_justificatif.chunks():
                    hasher.update(chunk)
                self.hash_sha256 = hasher.hexdigest()
            except Exception:
                pass

    def save(self, *args, **kwargs):
        """Immutabilité absolue : empêche toute mise à jour après création."""
        if not self._state.adding:
            raise ErreurMouvementImmuable(
                _("Un mouvement de stock est strictement immuable (RG-STK-05). "
                  "Pour corriger une erreur, créez un mouvement correctif inverse.")
            )
        if self.pk and MouvementStock.objects.filter(pk=self.pk).exists():
            raise ErreurMouvementImmuable(
                _("Un mouvement avec cet identifiant existe déjà en base et ne peut être modifié.")
            )
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        """Interdiction totale de suppression physique ou logique."""
        raise ErreurMouvementImmuable(
            _("Un mouvement de stock ne peut pas être supprimé (RG-STK-05). "
              "Toute régularisation se fait par contre-passation (mouvement inverse).")
        )

    def supprimer_definitivement(self, using=None, keep_parents=False):
        """Interdiction totale de suppression définitive."""
        raise ErreurMouvementImmuable(
            _("Un mouvement de stock ne peut pas être supprimé (RG-STK-05).")
        )

    @classmethod
    def creer_mouvement_correctif(
        cls,
        mouvement_original: "MouvementStock",
        auteur,
        motif: str,
        fichier_justificatif=None,
    ) -> "MouvementStock":
        """Crée un mouvement inverse pour annuler ou corriger un mouvement existant (RG-STK-05)."""
        if not motif or len(motif.strip()) < 10:
            raise ValidationError(
                _("Un motif d'au moins 10 caractères est requis pour un mouvement correctif.")
            )

        if mouvement_original.type_mouvement == TypeMouvementStock.ENTREE:
            type_corr = TypeMouvementStock.SORTIE
            qte = abs(mouvement_original.quantite)
        elif mouvement_original.type_mouvement == TypeMouvementStock.SORTIE:
            type_corr = TypeMouvementStock.ENTREE
            qte = abs(mouvement_original.quantite)
        elif mouvement_original.type_mouvement == TypeMouvementStock.INVENTAIRE:
            type_corr = TypeMouvementStock.INVENTAIRE
            qte = -mouvement_original.quantite
        else:
            type_corr = TypeMouvementStock.TRANSFERT
            qte = abs(mouvement_original.quantite)

        ref_corr = f"CORR-{mouvement_original.reference_piece or str(mouvement_original.id)[:8]}"

        mouvement_correctif = cls(
            entreprise=mouvement_original.entreprise,
            projet=mouvement_original.projet,
            lot=mouvement_original.lot,
            article=mouvement_original.article,
            type_mouvement=type_corr,
            quantite=qte,
            source=SourceMouvementStock.MANUEL,
            reference_piece=ref_corr,
            auteur=auteur,
            motif=f"Correction du mouvement {mouvement_original.id} : {motif.strip()}",
            mouvement_parent=mouvement_original,
            fichier_justificatif=fichier_justificatif,
        )
        mouvement_correctif.save()
        return mouvement_correctif
