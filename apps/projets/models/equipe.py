"""Équipes nommées et affectations métier, distinctes des droits d'accès projet."""

from django.conf import settings
from django.db import models

from apps.core.models import ModeleBase


class EquipeChantier(ModeleBase):
    projet = models.ForeignKey("projets.Projet", on_delete=models.RESTRICT, related_name="equipes")
    nom = models.CharField(max_length=200)
    nature = models.CharField(
        max_length=20,
        choices=[
            ("INTERNE", "Interne"),
            ("SOUS_TRAITANT", "Sous-traitant"),
            ("SOUS_TRAITANTE", "Sous-traitante"),
        ],
    )
    corps_etat = models.CharField(max_length=200)
    chef_utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="equipes_dirigees",
    )
    chef_nom = models.CharField(max_length=200, blank=True, default="")
    est_actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["cree_le", "id"]


class MembreEquipeChantier(ModeleBase):
    FONCTION_CHOICES = [
        ("CHEF_EQUIPE", "Chef d'équipe"),
        ("OUVRIER_QUALIFIE", "Ouvrier qualifié"),
        ("OUVRIER", "Ouvrier"),
        ("MANOEUVRE", "Manœuvre"),
        ("CONDUCTEUR_ENGIN", "Conducteur d'engin"),
        ("APPRENTI", "Apprenti"),
    ]

    equipe = models.ForeignKey(EquipeChantier, on_delete=models.RESTRICT, related_name="membres")
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="participations_equipes",
    )
    prenom = models.CharField(max_length=100, blank=True, default="")
    nom = models.CharField(max_length=200, blank=True, default="")
    fonction = models.CharField(max_length=50, choices=FONCTION_CHOICES, default="OUVRIER")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["equipe"],
                condition=models.Q(fonction="CHEF_EQUIPE", supprime_le__isnull=True),
                name="uq_membre_equipe_chef",
            )
        ]


class AffectationEquipeActivite(ModeleBase):
    equipe = models.ForeignKey(
        EquipeChantier,
        on_delete=models.RESTRICT,
        related_name="affectations_activites",
    )
    activite = models.ForeignKey(
        "projets.Activite",
        on_delete=models.RESTRICT,
        related_name="affectations_equipes",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["equipe", "activite"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_equipe_activite_active",
            )
        ]
