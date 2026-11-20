"""Modèles du calendrier d'entreprise — SFD F3 §6 & Erratum v1.0.1 (E-4).

Tables d'entreprise (`ModeleEntreprise`), application « projets ».

Règle des trois couches (de la plus faible à la plus forte) :
1. Semaine type (`SemaineType`) : jours de la semaine travaillés par défaut
   (lundi à vendredi par défaut).
2. Jours fériés nationaux : table partagée `referentiels.JourFerie`
   (plateforme, partagé entre toutes les entreprises).
3. Exceptions d'entreprise (`ExceptionCalendrier`) : date précise, sens ouvré
   ou non ouvré, et motif. Une exception l'emporte sur un jour férié national,
   qui l'emporte sur la semaine type.

Pourquoi ces modèles sont des tables d'entreprise de l'application « projets » :
Un calendrier unique s'applique à toute l'entreprise (partout où l'on compte des
jours ouvrés : avancement temporel, durée de projet, rapports journaliers attendus).
Chaque entreprise disposant de sa propre semaine type et de ses propres exceptions
(ex. fêtes musulmanes saisies par chaque entreprise comme exceptions non ouvrées),
ces données appartiennent strictement à l'entreprise (`ModeleEntreprise`)
et ne peuvent pas résider dans `referentiels` (partagé par toute la plateforme).
Il n'y a pas de calendrier propre à un projet.
"""

from __future__ import annotations

from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleEntreprise

__all__ = [
    "HEURE_DEBUT_DEFAUT",
    "HEURE_FIN_DEFAUT",
    "JOURS_SEMAINE",
    "ExceptionCalendrier",
    "SemaineType",
    "horaires_travail_par_defaut",
]

JOURS_SEMAINE: tuple[str, ...] = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
HEURE_DEBUT_DEFAUT = "07:30"
HEURE_FIN_DEFAUT = "17:00"


def horaires_travail_par_defaut() -> dict[str, dict[str, str]]:
    """Horaires par défaut de chaque jour de la semaine."""
    return {
        jour: {"debut": HEURE_DEBUT_DEFAUT, "fin": HEURE_FIN_DEFAUT}
        for jour in JOURS_SEMAINE
    }


class SemaineType(ModeleEntreprise):
    """Semaine type de travail d'une entreprise (ligne unique par entreprise).

    Première couche du calendrier d'entreprise : définit quels jours de la semaine
    sont réputés travaillés par défaut (du lundi au vendredi par défaut) ainsi que
    les horaires de travail (début et fin) de chaque jour ouvré.
    """

    cle = models.CharField(
        _("clé"),
        max_length=10,
        default="unique",
        editable=False,
    )
    lundi = models.BooleanField(_("lundi"), default=True)
    mardi = models.BooleanField(_("mardi"), default=True)
    mercredi = models.BooleanField(_("mercredi"), default=True)
    jeudi = models.BooleanField(_("jeudi"), default=True)
    vendredi = models.BooleanField(_("vendredi"), default=True)
    samedi = models.BooleanField(_("samedi"), default=False)
    dimanche = models.BooleanField(_("dimanche"), default=False)
    horaires_travail = models.JSONField(
        _("horaires de travail"),
        default=horaires_travail_par_defaut,
        blank=True,
    )

    class Meta:
        db_table = "semaine_type"
        verbose_name = _("semaine type")
        verbose_name_plural = _("semaines types")
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "cle"],
                name="uq_semaine_type_unique",
            )
        ]

    def __str__(self) -> str:
        return "Semaine type de l'entreprise"

    def jours_travailles(self) -> frozenset[int]:
        """Numéros date.weekday() (0 = lundi, ..., 6 = dimanche) des jours travaillés."""
        jours = set()
        if self.lundi:
            jours.add(0)
        if self.mardi:
            jours.add(1)
        if self.mercredi:
            jours.add(2)
        if self.jeudi:
            jours.add(3)
        if self.vendredi:
            jours.add(4)
        if self.samedi:
            jours.add(5)
        if self.dimanche:
            jours.add(6)
        return frozenset(jours)

    def horaires_normalises(self) -> dict[str, dict[str, str]]:
        """Rend les horaires de travail complets pour les 7 jours avec repli sur 07:30-17:00."""
        brut = self.horaires_travail if isinstance(self.horaires_travail, dict) else {}
        resultat: dict[str, dict[str, str]] = {}
        for jour in JOURS_SEMAINE:
            entree = brut.get(jour) if isinstance(brut.get(jour), dict) else {}
            debut = str(entree.get("debut") or HEURE_DEBUT_DEFAUT).strip()
            fin = str(entree.get("fin") or HEURE_FIN_DEFAUT).strip()
            resultat[jour] = {
                "debut": debut or HEURE_DEBUT_DEFAUT,
                "fin": fin or HEURE_FIN_DEFAUT,
            }
        return resultat

    def horaires_du_jour(self, jour: date) -> dict[str, str]:
        """Rend `{'heure_debut': 'HH:MM', 'heure_fin': 'HH:MM'}` pour la date donnée."""
        nom_jour = JOURS_SEMAINE[jour.weekday()]
        plage = self.horaires_normalises()[nom_jour]
        return {
            "heure_debut": plage["debut"],
            "heure_fin": plage["fin"],
        }

    @classmethod
    def courante(cls) -> SemaineType:
        """Rend l'unique ligne de l'entreprise.

        La crée avec les valeurs par défaut si elle n'existe pas.
        """
        instance, _ = cls.objects.get_or_create(cle="unique")
        return instance


class ExceptionCalendrier(ModeleEntreprise):
    """Exception de calendrier d'entreprise (troisième couche du calendrier).

    Prédomine sur les jours fériés nationaux et sur la semaine type.
    Permet de déclarer un jour ouvré malgré un jour férié ou un week-end,
    ou un jour non travaillé (ex. pont, fermeture exceptionnelle, fête religieuse musulmane).
    """

    date = models.DateField(_("date"))
    ouvre = models.BooleanField(
        _("jour ouvré"),
        help_text=_(
            "Vrai : jour travaillé malgré la semaine type ou un jour férié. "
            "Faux : jour non travaillé."
        ),
    )
    motif = models.CharField(_("motif"), max_length=150)

    class Meta:
        db_table = "exception_calendrier"
        verbose_name = _("exception de calendrier")
        verbose_name_plural = _("exceptions de calendrier")
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "date"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_exception_calendrier_date",
            )
        ]

    def __str__(self) -> str:
        statut = "ouvré" if self.ouvre else "non ouvré"
        return f"{self.date} ({statut}) : {self.motif}"
