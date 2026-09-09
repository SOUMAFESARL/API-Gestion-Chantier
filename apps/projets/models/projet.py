"""Modèles principaux pour l'application projets — MLD §6.1 et §6.4.

Schéma : tenant.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import RoleProjet, StatutProjet
from apps.core.models import ModeleBase

__all__ = ["AffectationProjet", "Projet"]


class Projet(ModeleBase):
    """Chantier / Projet de construction."""

    reference = models.CharField(_("référence"), max_length=30)
    nom = models.CharField(_("nom"), max_length=200)
    description = models.TextField(_("description"), blank=True)

    client = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        related_name="projets",
        verbose_name=_("client / maître d'ouvrage"),
    )

    ville = models.CharField(_("ville"), max_length=100)
    quartier = models.CharField(_("quartier"), max_length=150, blank=True)

    budget_initial_montant = models.BigIntegerField(
        _("budget initial (centimes)"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Montant en centimes de FCFA. Facultatif à la création."),
    )

    date_debut_prevue = models.DateField(_("date de début prévue"))
    date_fin_prevue = models.DateField(_("date de fin prévue"))

    date_debut_reelle = models.DateField(_("date de début réelle"), null=True, blank=True)
    date_fin_reelle = models.DateField(_("date de fin réelle"), null=True, blank=True)

    chef_projet = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.RESTRICT,
        related_name="projets_geres",
        verbose_name=_("chef de projet"),
    )

    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutProjet.choices,
        default=StatutProjet.EN_ATTENTE,
    )

    avancement_reel = models.DecimalField(
        _("avancement réel (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    avancement_theorique = models.DecimalField(
        _("avancement théorique (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    indice_sante = models.PositiveSmallIntegerField(
        _("indice de santé"),
        null=True,
        blank=True,
    )
    indice_sante_calcule_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "projet"
        verbose_name = _("projet")
        verbose_name_plural = _("projets")
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        return f"{self.reference} — {self.nom}"


class AffectationProjet(ModeleBase):
    """Affectation d'un utilisateur à un projet avec un rôle spécifique."""

    utilisateur = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.CASCADE,
        related_name="affectations",
    )
    projet = models.ForeignKey(
        Projet,
        on_delete=models.CASCADE,
        related_name="affectations",
    )
    role_projet = models.CharField(
        _("rôle sur le projet"),
        max_length=5,
        choices=RoleProjet.choices,
        default=RoleProjet.CHEF_PROJET,
    )
    role = models.ForeignKey(
        "accounts.Role",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affectations_projets",
        verbose_name=_("rôle personnalisé"),
    )
    date_debut = models.DateField(_("date de début"), default=timezone.now)
    date_fin = models.DateField(_("date de fin"), null=True, blank=True)
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "affectation_projet"
        verbose_name = _("affectation au projet")
        verbose_name_plural = _("affectations aux projets")
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "projet"],
                name="uq_affectation_utilisateur_projet",
            )
        ]

    def __str__(self) -> str:
        return f"{self.utilisateur} sur {self.projet.nom} ({self.get_role_projet_display()})"
