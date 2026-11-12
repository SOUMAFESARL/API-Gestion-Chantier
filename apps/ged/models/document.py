"""Modèle Document — Classeur projet de la GED CCD Digital.

Entité principale de la Gestion Documentaire Minimale (F6 MVP).
Table d'entreprise (`ModeleEntreprise` — isolation D9).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CategorieDocument
from apps.core.models import ModeleEntreprise
from apps.ged.models.exceptions import DocumentAutomatiqueNonSupprimable


class Document(ModeleEntreprise):
    """Document rattaché à un projet de construction.

    Chaque document appartient à l'une des 6 catégories métier BTP.
    Un document marqué `est_automatique=True` (remonté de F1, F2 ou F9)
    est inaltérable et ne peut être supprimé par personne.
    """

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.RESTRICT,
        related_name="documents",
        verbose_name=_("projet"),
        db_index=True,
    )
    categorie = models.CharField(
        _("catégorie"),
        max_length=50,
        choices=CategorieDocument.choices,
        db_index=True,
        help_text=_(
            "Catégorie métier BTP (PLANS, CONTRATS, RAPPORTS, ADMINISTRATIF, PHOTOS, DIVERS)."
        ),
    )
    nom = models.CharField(
        _("nom"),
        max_length=255,
        help_text=_("Nom usuel ou titre du document."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Description facultative ou contexte du document."),
    )
    est_reference = models.BooleanField(
        _("document de référence"),
        default=False,
        db_index=True,
        help_text=_("Épinglé en tête du classeur projet (étoile)."),
    )
    est_automatique = models.BooleanField(
        _("généré automatiquement"),
        default=False,
        db_index=True,
        help_text=_(
            "Document alimenté automatiquement par F1, F2 ou F9. Inaltérable et non supprimable."
        ),
    )
    createur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="documents_crees",
        verbose_name=_("créateur"),
        help_text=_("Utilisateur ayant déposé le document (nul si système)."),
    )

    class Meta:
        db_table = "document"
        verbose_name = _("document")
        verbose_name_plural = _("documents")
        ordering = ["-est_reference", "-cree_le"]
        indexes = [
            models.Index(fields=["entreprise", "projet", "categorie"], name="idx_doc_ent_proj_cat"),
            models.Index(fields=["projet", "est_reference"], name="idx_doc_proj_ref"),
            models.Index(fields=["projet", "est_automatique"], name="idx_doc_proj_auto"),
            models.Index(fields=["projet", "supprime_le"], name="idx_doc_proj_suppr"),
        ]

    def __str__(self) -> str:
        return f"{self.nom} ({self.get_categorie_display()})"

    # -- Propriétés de commodité & compatibilité MLD ------------------------

    @property
    def libelle(self) -> str:
        """Alias pour le champ `nom` (MLD §5.7)."""
        return self.nom

    @libelle.setter
    def libelle(self, val: str) -> None:
        self.nom = val

    @property
    def date(self):
        """Date de création du document."""
        return self.cree_le

    @property
    def derniere_version(self):
        """Retourne la version active ou la plus récente du document."""
        return (
            self.versions.filter(est_active=True).first()
            or self.versions.order_by("-numero_version").first()
        )

    @property
    def nombre_versions(self) -> int:
        """Nombre total de versions enregistrées."""
        return self.versions.count()

    # -- Intégrité et protection contre la suppression -----------------------

    def clean(self):
        super().clean()
        if self.est_automatique and self.supprime_le is not None:
            raise DocumentAutomatiqueNonSupprimable()

    def save(self, *args, **kwargs):
        # Synchronisation créateur / cree_par du socle
        if self.createur_id and not self.cree_par_id:
            self.cree_par_id = self.createur_id
        elif self.cree_par_id and not self.createur_id:
            self.createur_id = self.cree_par_id

        # Règle F6 §5 : protection absolue des documents automatiques
        if self.est_automatique and self.supprime_le is not None:
            raise DocumentAutomatiqueNonSupprimable()

        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        """Suppression logique protégée : interdite pour les documents automatiques."""
        if self.est_automatique:
            raise DocumentAutomatiqueNonSupprimable()
        return super().delete(using=using, keep_parents=keep_parents, utilisateur=utilisateur)

    def supprimer_definitivement(self, using=None, keep_parents=False):
        """Suppression physique : strictement interdite pour les documents automatiques."""
        if self.est_automatique:
            raise DocumentAutomatiqueNonSupprimable()
        return super().supprimer_definitivement(using=using, keep_parents=keep_parents)
