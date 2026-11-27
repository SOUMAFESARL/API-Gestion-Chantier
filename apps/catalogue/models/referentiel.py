"""Référentiels de la plateforme — types de projet et modes d'exécution (table de plateforme).

Posés par le super admin, ils sont proposés à toutes les entreprises, qui y
ajoutent les leurs (`projets.ReferentielEntreprise`) sans pouvoir retirer
ceux-ci. Arbitrage du 16/10/2026.

La catégorie `LOT` n'est plus exposée par aucune route : elle est devenue la liste de valeurs
« Lots » du découpage (décisions v1.2, §4.2 ; `catalogue/migrations/0014_peupler_decoupage.py`).
Elle reste dans les choix pour que les lignes déjà en base restent valides.
"""

import re
import unicodedata

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = [
    "FONCTIONS_EQUIPE_INITIALES",
    "CategorieReferentiel",
    "ReferentielPlateforme",
    "cle_comparaison",
    "code_depuis_libelle",
    "ensemencer_fonctions_equipe",
]


class CategorieReferentiel(models.TextChoices):
    TYPE_PROJET = "TYPE_PROJET", _("Catégorie d'ouvrage")
    LOT = "LOT", _("Nom de lot")  # plus exposée : voir la liste « Lots » du découpage
    MODE_EXECUTION = "MODE_EXECUTION", _("Mode d'exécution")
    FONCTION_EQUIPE = "FONCTION_EQUIPE", _("Fonction / métier de chantier")


FONCTIONS_EQUIPE_INITIALES: tuple[tuple[str, str, str], ...] = (
    ("Qualification générale", "OUVRIER_QUALIFIE", "Ouvrier qualifié"),
    ("Qualification générale", "OUVRIER", "Ouvrier"),
    ("Qualification générale", "MANOEUVRE", "Manœuvre"),
    ("Qualification générale", "APPRENTI", "Apprenti"),
    ("Gros œuvre", "MACON", "Maçon"),
    ("Gros œuvre", "FERRAILLEUR", "Ferrailleur"),
    ("Gros œuvre", "COFFREUR", "Coffreur"),
    ("Gros œuvre", "BETONNEUR", "Bétonneur"),
    ("Second œuvre & Technique", "ELECTRICIEN", "Électricien"),
    ("Second œuvre & Technique", "PLOMBIER", "Plombier"),
    ("Second œuvre & Technique", "CARRELEUR", "Carreleur"),
    ("Second œuvre & Technique", "PEINTRE", "Peintre"),
    ("Second œuvre & Technique", "MENUISIER", "Menuisier"),
    ("Second œuvre & Technique", "SOUDEUR", "Soudeur"),
    ("Engins & Logistique", "CONDUCTEUR_ENGIN", "Conducteur d'engin"),
    ("Engins & Logistique", "GRUTIER", "Grutier"),
    ("Engins & Logistique", "CHAUFFEUR", "Chauffeur"),
    ("Engins & Logistique", "MAGASINIER", "Magasinier"),
)


def ensemencer_fonctions_equipe(modele=None) -> None:
    """Ensemence de façon idempotente les fonctions/métiers d'équipe plateforme."""
    cible = modele or ReferentielPlateforme
    gestionnaire = getattr(cible, "_base_manager", cible.objects)
    for ordre, (groupe, code, libelle) in enumerate(FONCTIONS_EQUIPE_INITIALES, start=1):
        gestionnaire.get_or_create(
            categorie=CategorieReferentiel.FONCTION_EQUIPE,
            code=code,
            supprime_le__isnull=True,
            defaults={"libelle": libelle, "groupe": groupe, "ordre": ordre},
        )


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
