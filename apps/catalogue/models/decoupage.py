"""Listes de valeurs et modèles de découpage de la plateforme (schéma public).

Décisions v1.2 du découpage, §3 et §4 :

- **Les listes sont des données** (« Phases », « Lots »…), pas une énumération codée. Le super
  admin crée les listes plateforme ; chaque entreprise les lit sans copie, y ajoute ses propres
  valeurs et crée ses propres listes (`projets.ListeValeursEntreprise`), sans pouvoir retirer
  une valeur plateforme.
- **Un modèle de découpage** est un gabarit — des niveaux ordonnés, chacun puisant au plus dans
  une liste — accompagné de **lignes types** : une ligne = une feuille, ses cellules suivent les
  niveaux. Un modèle plateforme existe une seule fois ici, et toutes les entreprises le lisent :
  une correction du super admin est vue partout immédiatement.
- **Un modèle plateforme ne puise que dans des listes plateforme.**
- Un modèle déclare les types de projet pour lesquels il est conçu ; le modèle **par défaut**
  d'un type est celui qui pré-remplit le tableau de démarrage d'un projet de ce type.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

from .referentiel import cle_comparaison

__all__ = [
    "LigneModelePlateforme",
    "ListeValeursPlateforme",
    "ModeleDecoupagePlateforme",
    "NiveauModelePlateforme",
    "ValeurListePlateforme",
]


class ListeValeursPlateforme(ModeleBase):
    libelle = models.CharField(_("libellé"), max_length=100)
    description = models.TextField(_("description"), blank=True, default="")
    ordre = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        db_table = "catalogue_liste_valeurs"
        verbose_name = _("liste de valeurs plateforme")
        verbose_name_plural = _("listes de valeurs plateforme")
        ordering = ["ordre", "libelle"]

    def __str__(self) -> str:
        return self.libelle


class ValeurListePlateforme(ModeleBase):
    liste = models.ForeignKey(
        ListeValeursPlateforme, on_delete=models.CASCADE, related_name="valeurs"
    )
    libelle = models.CharField(_("libellé"), max_length=200)
    # Titre de groupe dans la liste déroulante (le corps d'état d'un lot, par exemple).
    groupe = models.CharField(_("groupe"), max_length=100, blank=True, default="")
    cle_comparaison = models.CharField(max_length=200, editable=False, default="")
    ordre = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        db_table = "catalogue_valeur_liste"
        verbose_name = _("valeur de liste plateforme")
        verbose_name_plural = _("valeurs de liste plateforme")
        ordering = ["ordre", "libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["liste", "cle_comparaison"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_catalogue_valeur_liste_cle",
            )
        ]

    def save(self, *args, **kwargs):
        self.cle_comparaison = cle_comparaison(self.libelle)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.libelle


class ModeleDecoupagePlateforme(ModeleBase):
    nom = models.CharField(_("nom"), max_length=150)
    description = models.TextField(_("description"), blank=True, default="")
    # Codes des types de projet pour lesquels le modèle est conçu (référentiel TYPE_PROJET).
    types_projet = models.JSONField(_("types de projet"), default=list, blank=True)
    # Les types de projet dont ce modèle pré-remplit le tableau de démarrage.
    par_defaut_pour = models.JSONField(_("modèle par défaut pour"), default=list, blank=True)
    # Incrémentée à chaque modification : une copie personnalisée sait dire qu'elle est en retard.
    version = models.PositiveIntegerField(_("version"), default=1)
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "catalogue_modele_decoupage"
        verbose_name = _("modèle de découpage plateforme")
        verbose_name_plural = _("modèles de découpage plateforme")
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom


class NiveauModelePlateforme(ModeleBase):
    modele = models.ForeignKey(
        ModeleDecoupagePlateforme, on_delete=models.CASCADE, related_name="niveaux"
    )
    ordre = models.PositiveSmallIntegerField(_("ordre"))
    libelle = models.CharField(_("libellé"), max_length=60)
    liste = models.ForeignKey(
        ListeValeursPlateforme,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="niveaux_modeles",
    )
    # « Alerter à ce niveau » (§13quater-ter) : où naissent les alertes de retard.
    alerter = models.BooleanField(_("alerter à ce niveau"), default=False)

    class Meta:
        db_table = "catalogue_niveau_modele_decoupage"
        ordering = ["modele", "ordre"]
        constraints = [
            models.UniqueConstraint(
                fields=["modele", "ordre"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_catalogue_niveau_modele_ordre",
            )
        ]

    def __str__(self) -> str:
        return f"{self.modele} — {self.ordre}. {self.libelle}"


class LigneModelePlateforme(ModeleBase):
    modele = models.ForeignKey(
        ModeleDecoupagePlateforme, on_delete=models.CASCADE, related_name="lignes"
    )
    ordre = models.PositiveIntegerField(_("ordre"), default=0)
    # Une cellule par niveau, dans l'ordre des niveaux ; les dernières peuvent être vides.
    valeurs = models.JSONField(_("valeurs"), default=list)

    class Meta:
        db_table = "catalogue_ligne_modele_decoupage"
        ordering = ["modele", "ordre"]
