"""Modèle ArticleCatalogue — Référentiel matériaux et équipements BTP (SFD F9-1).

Table d'entreprise (`ModeleEntreprise`), partagée au niveau du tenant (commune aux chantiers).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CategorieArticle, UniteMesure
from apps.core.fields import QuantiteField
from apps.core.models import ModeleEntreprise

__all__ = ["ArticleCatalogue", "CategorieArticle"]


class ArticleCatalogue(ModeleEntreprise):
    """Article du catalogue partagé au niveau de l'entreprise.

    Porte le code unique par entreprise, la désignation, la catégorie (distinction clé
    matériau vs équipement pour les circuits de validation F9), l'unité de mesure et le seuil
    d'alerte par défaut (SFD F9-1).
    """

    code = models.CharField(
        _("code article"),
        max_length=50,
        db_index=True,
        help_text=_(
            "Code unique d'identification dans l'entreprise (ex: CIM-425, GRA-2040, FER-HA12)."
        ),
    )
    designation = models.CharField(
        _("désignation"),
        max_length=200,
        help_text=_("Désignation commerciale ou technique de l'article."),
    )
    categorie = models.CharField(
        _("catégorie"),
        max_length=20,
        choices=CategorieArticle.choices,
        default=CategorieArticle.MATERIAU,
        db_index=True,
        help_text=_(
            "Catégorie d'article : MATERIAU, EQUIPEMENT (validation 2 niveaux CT+CP), etc."
        ),
    )
    famille = models.CharField(
        _("famille / corps d'état"),
        max_length=100,
        blank=True,
        default="",
        help_text=_(
            "Famille BTP libre ou corps d'état (ex: Gros œuvre, Granulats, Aciers, Bois, etc.)."
        ),
    )
    unite_mesure = models.CharField(
        _("unité de mesure"),
        max_length=20,
        choices=UniteMesure.choices,
        default=UniteMesure.UNITE,
        help_text=_("Unité de comptage pour les mouvements et inventaires."),
    )
    seuil_alerte_defaut = QuantiteField(
        _("seuil d'alerte par défaut"),
        default=0,
        help_text=_(
            "Seuil d'alerte initial proposé au premier approvisionnement sur un lot."
        ),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Précisions techniques ou spécifications du matériau."),
    )
    est_actif = models.BooleanField(
        _("est actif"),
        default=True,
        help_text=_("Désactiver pour masquer des formulaires sans casser l'historique."),
    )

    class Meta:
        db_table = "article_catalogue"
        verbose_name = _("article du catalogue")
        verbose_name_plural = _("articles du catalogue")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_article_catalogue_code_actif",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.designation}"
