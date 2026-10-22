"""Réglage de l'en-tête et du pied de page des documents PDF de l'entreprise.

Schéma : tenant (application « projets »).

Tous les PDF (fiche projet, rapport journalier, synthèse, bons de stock) sont
dessinés dans le navigateur ; le serveur ne fait que stocker ce que
l'entreprise veut y lire, et le résoudre en lignes prêtes à imprimer.

Une seule ligne par entreprise, comme `SemaineType` : accès par `courante()`.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = ["CODES_MENTIONS", "ParametresDocuments"]

# Codes de mentions admis dans l'en-tête et dans le pied, dans l'ordre où
# l'écran de réglage les propose. La liste stockée est ordonnée : l'ordre choisi
# par l'entreprise est l'ordre d'impression.
CODES_MENTIONS = (
    "raison_sociale",
    "nom_commercial",
    "rccm",
    "nif",
    "adresse",
    "ville",
    "telephone",
    "email",
    "site_web",
)


def mentions_entete_par_defaut() -> list[str]:
    return ["raison_sociale", "rccm", "nif"]


def mentions_pied_par_defaut() -> list[str]:
    return ["raison_sociale", "adresse", "telephone"]


class ParametresDocuments(ModeleBase):
    """Réglage de l'en-tête et du pied des documents (ligne unique par schéma tenant)."""

    cle = models.CharField(
        _("clé"),
        max_length=10,
        default="unique",
        editable=False,
    )
    entete_afficher_logo = models.BooleanField(_("afficher le logo dans l'en-tête"), default=True)
    entete_mentions = models.JSONField(
        _("mentions de l'en-tête"),
        default=mentions_entete_par_defaut,
        help_text=_("Liste ordonnée de codes de mentions."),
    )
    entete_texte_libre = models.CharField(
        _("texte libre de l'en-tête"), max_length=200, blank=True, default=""
    )
    pied_mentions = models.JSONField(
        _("mentions du pied de page"),
        default=mentions_pied_par_defaut,
        help_text=_("Liste ordonnée de codes de mentions."),
    )
    pied_texte_libre = models.CharField(
        _("texte libre du pied de page"),
        max_length=300,
        blank=True,
        default="",
        help_text=_("Par exemple le capital social ou des mentions légales."),
    )

    class Meta:
        db_table = "parametres_documents"
        verbose_name = _("paramètres des documents")
        verbose_name_plural = _("paramètres des documents")
        constraints = [
            models.UniqueConstraint(
                fields=["cle"],
                name="uq_parametres_documents_unique",
            )
        ]

    def __str__(self) -> str:
        return "Paramètres des documents de l'entreprise"

    @classmethod
    def courant(cls) -> ParametresDocuments:
        """Rend l'unique ligne de l'entreprise.

        La crée avec les valeurs par défaut si elle n'existe pas.
        """
        instance, _ = cls.objects.get_or_create(cle="unique")
        return instance
