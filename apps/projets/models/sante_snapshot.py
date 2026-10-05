"""Modèle SanteProjetSnapshot — Historique immuable des calculs d'indice de santé.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets) & 4 (Pilotage).
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import BadgeSante
from apps.core.models import ModeleBase

__all__ = ["SanteProjetSnapshot"]


class SanteProjetSnapshot(ModeleBase):
    """Snapshot historique d'un calcul d'indice de santé pour un projet (conservation illimitée)."""

    projet = models.ForeignKey(
        "projets.Projet",
        on_delete=models.CASCADE,
        related_name="snapshots_sante",
        verbose_name=_("projet"),
    )
    date_calcul = models.DateTimeField(
        _("date de calcul"),
        default=timezone.now,
        db_index=True,
    )
    declencheur_type = models.CharField(
        _("type de déclencheur"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Origine du recalcul (ex: RAPPORT, BLOCAGE, ARRET, REPROGRAMMATION, JOB_QUOTIDIEN)."),
    )
    declencheur_id = models.CharField(
        _("identifiant du déclencheur"),
        max_length=100,
        blank=True,
        default="",
    )

    # Scores et badges
    score = models.PositiveSmallIntegerField(
        _("score de santé"),
        help_text=_("Score global de 0 à 100."),
    )
    badge_brut = models.CharField(
        _("badge brut"),
        max_length=10,
        choices=BadgeSante.choices,
    )
    badge_final = models.CharField(
        _("badge final"),
        max_length=10,
        choices=BadgeSante.choices,
        help_text=_("Badge après application éventuelle du plancher de gravité."),
    )
    plancher_applique = models.BooleanField(
        _("plancher de gravité appliqué"),
        default=False,
    )

    # Décomposition des pénalités
    p_delais = models.DecimalField(
        _("pénalité délais (0-40)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    p_retard = models.DecimalField(
        _("sous-pénalité retard"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    p_malus = models.DecimalField(
        _("sous-pénalité malus reports"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    p_blocages = models.DecimalField(
        _("pénalité blocages (0-40)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    p_reporting = models.DecimalField(
        _("pénalité reporting (0-20)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    # Données brutes de calcul
    avancement_physique = models.DecimalField(
        _("avancement physique (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    avancement_temporel = models.DecimalField(
        _("avancement temporel (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    delta = models.DecimalField(
        _("retard en points (temporel - physique)"),
        max_digits=6,
        decimal_places=2,
        default=0,
    )
    mode_ponderation = models.CharField(
        _("mode de pondération"),
        max_length=20,
        default="UNIFORME",
    )
    nb_reports = models.PositiveIntegerField(
        _("nombre de reports accordés"),
        default=0,
    )
    blocages_ouverts_par_severite = models.JSONField(
        _("blocages ouverts par sévérité"),
        default=dict,
    )
    taux_reporting = models.DecimalField(
        _("taux de reporting"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    jours_attendus = models.PositiveSmallIntegerField(
        _("jours attendus"),
        default=0,
    )
    jours_couverts = models.PositiveSmallIntegerField(
        _("jours couverts"),
        default=0,
    )

    class Meta:
        db_table = "sante_projet_snapshot"
        verbose_name = _("snapshot de santé projet")
        verbose_name_plural = _("snapshots de santé projet")
        ordering = ["-date_calcul"]
        indexes = [
            # C7 : SanteProjetSnapshot indexé sur (projet, date de calcul décroissante)
            models.Index(fields=["projet", "-date_calcul"], name="idx_sante_snap_proj_date"),
        ]

    def __str__(self) -> str:
        return f"Snapshot {self.projet.reference} au {self.date_calcul:%d/%m/%Y %H:%M} : {self.score} ({self.badge_final})"
