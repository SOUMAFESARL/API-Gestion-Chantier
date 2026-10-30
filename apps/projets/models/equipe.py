"""Équipes de chantier et registre de main-d'œuvre — qui travaille où.

Distinctes des droits d'accès (`AffectationProjet`) : une équipe dit **quelles personnes** sont
sur place ; l'exécutant d'une case dit qui **répond** du travail, le mode d'exécution **comment**
on le suit (décision validée le 29/10/2026).

- **Le registre de main-d'œuvre** (`PersonneMainOeuvre`) est tenu au niveau de l'entreprise :
  nom et prénom obligatoires, téléphone facultatif. Une personne appartient à notre entreprise
  ou à une entreprise partenaire (sous-traitant, tâcheron), et peut avoir un compte sur la
  plateforme. Les membres d'une équipe sont choisis dans ce registre.
- **Une équipe est rattachée à une entreprise** : la nôtre (`entreprise_partenaire` vide) ou un
  partenaire. Sa « nature » n'est plus saisie : elle se déduit de ce rattachement.
- **Un seul chef d'équipe**, qui fait partie des membres, avec ou sans compte.
- **Les membres ont une date d'arrivée et de départ** : l'historique de l'équipe se garde.
- **Une équipe s'affecte à n'importe quelle case** de l'arbre et vaut pour tout le sous-arbre ;
  une case peut recevoir plusieurs équipes, et l'affectation la plus précise l'emporte (§13bis).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

__all__ = [
    "AffectationEquipeElement",
    "EquipeChantier",
    "MembreEquipeChantier",
    "PersonneMainOeuvre",
]


class PersonneMainOeuvre(ModeleBase):
    nom = models.CharField(_("nom"), max_length=150)
    prenom = models.CharField(_("prénom"), max_length=150)
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True, default="")
    # Vide : la personne est de notre entreprise ; sinon, de ce partenaire.
    entreprise_partenaire = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="main_oeuvre",
    )
    # Le compte de la personne sur la plateforme, si elle en a un.
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_main_oeuvre",
    )
    metier = models.CharField(_("métier"), max_length=100, blank=True, default="")
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "personne_main_oeuvre"
        verbose_name = _("personne du registre de main-d'œuvre")
        ordering = ["nom", "prenom"]
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur"],
                condition=models.Q(supprime_le__isnull=True, utilisateur__isnull=False),
                name="uq_main_oeuvre_utilisateur",
            )
        ]

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}".strip()

    def __str__(self) -> str:
        return self.nom_complet


class EquipeChantier(ModeleBase):
    projet = models.ForeignKey("projets.Projet", on_delete=models.RESTRICT, related_name="equipes")
    nom = models.CharField(_("nom"), max_length=200)
    corps_etat = models.CharField(_("corps d'état"), max_length=200, blank=True, default="")
    # Vide : équipe de notre entreprise ; sinon, d'un partenaire.
    entreprise_partenaire = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="equipes_chantier",
    )
    est_actif = models.BooleanField(_("est active"), default=True)

    class Meta:
        db_table = "equipe_chantier"
        ordering = ["cree_le", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "nom"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_equipe_nom_projet",
            )
        ]

    @property
    def nature(self) -> str:
        """Déduite du rattachement, jamais saisie."""
        return "PARTENAIRE" if self.entreprise_partenaire_id else "INTERNE"

    def __str__(self) -> str:
        return self.nom


class MembreEquipeChantier(ModeleBase):
    FONCTION_CHOICES = [
        ("CHEF_EQUIPE", _("Chef d'équipe")),
        ("OUVRIER_QUALIFIE", _("Ouvrier qualifié")),
        ("OUVRIER", _("Ouvrier")),
        ("MANOEUVRE", _("Manœuvre")),
        ("CONDUCTEUR_ENGIN", _("Conducteur d'engin")),
        ("APPRENTI", _("Apprenti")),
    ]

    equipe = models.ForeignKey(EquipeChantier, on_delete=models.RESTRICT, related_name="membres")
    personne = models.ForeignKey(
        PersonneMainOeuvre, on_delete=models.RESTRICT, related_name="appartenances"
    )
    fonction = models.CharField(max_length=50, choices=FONCTION_CHOICES, default="OUVRIER")
    est_chef = models.BooleanField(_("chef d'équipe"), default=False)
    date_arrivee = models.DateField(_("date d'arrivée"))
    date_depart = models.DateField(_("date de départ"), null=True, blank=True)

    class Meta:
        db_table = "membre_equipe_chantier"
        ordering = ["-est_chef", "date_arrivee", "cree_le"]
        constraints = [
            # Un seul chef d'équipe à la fois.
            models.UniqueConstraint(
                fields=["equipe"],
                condition=models.Q(est_chef=True, supprime_le__isnull=True),
                name="uq_membre_equipe_chef",
            ),
            # Une personne n'est qu'une fois membre en cours d'une même équipe.
            models.UniqueConstraint(
                fields=["equipe", "personne"],
                condition=models.Q(supprime_le__isnull=True, date_depart__isnull=True),
                name="uq_membre_equipe_personne_en_cours",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(date_depart__isnull=True)
                    | models.Q(date_depart__gte=models.F("date_arrivee"))
                ),
                name="chk_membre_equipe_dates",
            ),
        ]


class AffectationEquipeElement(ModeleBase):
    equipe = models.ForeignKey(
        EquipeChantier, on_delete=models.RESTRICT, related_name="affectations_elements"
    )
    element = models.ForeignKey(
        "projets.Element", on_delete=models.RESTRICT, related_name="affectations_equipes"
    )

    class Meta:
        db_table = "affectation_equipe_element"
        constraints = [
            models.UniqueConstraint(
                fields=["equipe", "element"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_equipe_element_active",
            )
        ]
