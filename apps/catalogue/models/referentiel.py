"""Référentiels de la plateforme — types de projet et noms de lot (schéma public).

Posés par le super admin, ils sont proposés à toutes les entreprises, qui y
ajoutent les leurs (`projets.ReferentielEntreprise`) sans pouvoir retirer
ceux-ci. Arbitrage du 16/10/2026.
"""

import re
import unicodedata

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = [
    "CategorieReferentiel",
    "ReferentielPlateforme",
    "cle_comparaison",
    "code_depuis_libelle",
]


class CategorieReferentiel(models.TextChoices):
    TYPE_PROJET = "TYPE_PROJET", _("Type de projet")
    LOT = "LOT", _("Nom de lot")
    MODE_EXECUTION = "MODE_EXECUTION", _("Mode d'exécution")


def cle_comparaison(libelle: str) -> str:
    """« Gros Œuvre » et « gros oeuvre » sont le même libellé : sans accents, casse ni espaces."""
    texte = unicodedata.normalize("NFKD", (libelle or "").replace("œ", "oe").replace("Œ", "OE"))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texte).strip().lower()


def code_depuis_libelle(libelle: str) -> str:
    """`Bâtiment — Résidentiel` → `BATIMENT_RESIDENTIEL` (60 caractères au plus)."""
    code = re.sub(r"[^A-Za-z0-9]+", "_", cle_comparaison(libelle)).strip("_").upper()
    return (code or "ENTREE")[:60]


class ReferentielPlateforme(ModeleBase):
    categorie = models.CharField(
        _("catégorie"), max_length=20, choices=CategorieReferentiel.choices
    )
    code = models.CharField(_("code"), max_length=60)
    libelle = models.CharField(_("libellé"), max_length=150)
    groupe = models.CharField(
        _("groupe"),
        max_length=100,
        blank=True,
        default="",
        help_text=_(
            "Titre de groupe dans la liste — le corps d'état d'un lot ; "
            "pour un mode d'exécution, le mode de base auquel il se rattache."
        ),
    )
    ordre = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        db_table = "catalogue_referentiel"
        verbose_name = _("entrée de référentiel plateforme")
        verbose_name_plural = _("référentiels plateforme")
        ordering = ["categorie", "ordre", "libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["categorie", "code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_catalogue_referentiel_code_actif",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_categorie_display()} — {self.libelle}"
