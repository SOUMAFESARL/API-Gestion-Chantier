"""Référentiels propres à une entreprise — types de projet et noms de lot (schéma tenant).

Ils complètent ceux de la plateforme (`catalogue.ReferentielPlateforme`) :
l'entreprise ajoute et retire les siens, jamais ceux de la plateforme.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalogue.models.referentiel import CategorieReferentiel
from apps.core.models import ModeleBase

__all__ = ["ReferentielEntreprise"]


class ReferentielEntreprise(ModeleBase):
    categorie = models.CharField(
        _("catégorie"), max_length=20, choices=CategorieReferentiel.choices
    )
    code = models.CharField(_("code"), max_length=60)
    libelle = models.CharField(_("libellé"), max_length=150)
    groupe = models.CharField(_("groupe"), max_length=100, blank=True, default="")

    class Meta:
        db_table = "referentiel_entreprise"
        verbose_name = _("entrée de référentiel de l'entreprise")
        verbose_name_plural = _("référentiels de l'entreprise")
        ordering = ["categorie", "libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["categorie", "code"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_referentiel_entreprise_code_actif",
            )
        ]

    def __str__(self) -> str:
        return self.libelle
