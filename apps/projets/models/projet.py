"""Modèles principaux pour l'application projets — MLD §6.1 et §6.4.

Schéma : tenant.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import BadgeSante, RoleProjet, StatutProjet, TypeProjet
from apps.core.models import ModeleBase

__all__ = ["AffectationProjet", "Projet"]


class Projet(ModeleBase):
    """Chantier / Projet de construction."""

    reference = models.CharField(_("référence"), max_length=30)
    nom = models.CharField(_("nom"), max_length=200)
    # Code d'une entrée des référentiels (plateforme ou entreprise) — plus de liste figée.
    type_projet = models.CharField(
        _("type de projet"),
        max_length=60,
        default=TypeProjet.BATIMENT_RESIDENTIEL,
    )
    description = models.TextField(_("description"), blank=True)

    client = models.ForeignKey(
        "tiers.Tiers",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="projets",
        verbose_name=_("client / maître d'ouvrage"),
    )
    maitre_ouvrage = models.CharField(_("maître d'ouvrage"), max_length=200, blank=True)
    maitre_oeuvre = models.CharField(
        _("maître d'œuvre"),
        max_length=200,
        blank=True,
        help_text=_("Cabinet ou bureau d'études (optionnel)."),
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

    date_debut_prevue = models.DateField(_("date de début prévue"), null=True, blank=True)
    date_fin_prevue = models.DateField(_("date de fin prévue"), null=True, blank=True)

    date_debut_baseline = models.DateField(
        _("date de début baseline v0"),
        null=True,
        blank=True,
        help_text=_("Date de début contractuelle initiale (figée, intacte)."),
    )
    date_fin_baseline = models.DateField(
        _("date de fin baseline v0"),
        null=True,
        blank=True,
        help_text=_("Date de fin contractuelle initiale (figée, intacte)."),
    )

    date_debut_reelle = models.DateField(_("date de début réelle"), null=True, blank=True)
    date_fin_reelle = models.DateField(_("date de fin réelle"), null=True, blank=True)

    chef_projet = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projets_geres",
        verbose_name=_("chef de projet"),
    )
    conducteur_travaux = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="projets_chantiers",
        verbose_name=_("conducteur de travaux"),
    )
    sans_chef_projet = models.BooleanField(_("sans chef de projet"), default=False)

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
        help_text=_(
            "Déprécié : valeur de l'ancien moteur, plus lue ; "
            "l'avancement temporel se calcule à chaque appel (SFD F3 RG-F3-04)."
        ),
    )

    indice_sante = models.PositiveSmallIntegerField(
        _("indice de santé"),
        null=True,
        blank=True,
    )
    indice_sante_calcule_le = models.DateTimeField(null=True, blank=True)
    badge_sante = models.CharField(
        _("badge de santé"),
        max_length=10,
        choices=BadgeSante.choices,
        null=True,
        blank=True,
        help_text=_("Badge final (après application du plancher de gravité)."),
    )

    @property
    def duree_jours_ouvres(self) -> int | None:
        """Calcule la durée estimée en jours ouvrés selon le calendrier de l'entreprise."""
        if not self.date_debut_prevue or not self.date_fin_prevue:
            return None
        if self.date_fin_prevue < self.date_debut_prevue:
            return 0
        from apps.projets.services.calendrier_ouvre import calendrier_entreprise
        from apps.projets.services.sante_calculs import compter_jours_ouvres

        return compter_jours_ouvres(
            self.date_debut_prevue,
            self.date_fin_prevue,
            calendrier_entreprise(self.date_debut_prevue, self.date_fin_prevue),
        )

    @property
    def duree_calendaire(self) -> dict[str, int] | None:
        """Calcule la durée du projet en années, mois, jours et jours ouvrés."""
        from apps.projets.services.durees import duree_calendaire

        duree = duree_calendaire(self.date_debut_prevue, self.date_fin_prevue)
        if duree is None:
            return None
        return {
            **duree,
            "jours_ouvres": self.duree_jours_ouvres,
        }

    class Meta:
        db_table = "projet"
        verbose_name = _("projet")
        verbose_name_plural = _("projets")
        ordering = ["-cree_le"]
        constraints = [
            models.UniqueConstraint(
                fields=["reference"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_projet_reference_tenant",
            )
        ]

    def save(self, *args, **kwargs):
        """Initialise la Baseline v0 à la première sauvegarde si non définie."""
        if self.chef_projet_id is not None or self.chef_projet is not None:
            self.sans_chef_projet = False
        if self.date_debut_baseline is None and self.date_debut_prevue:
            self.date_debut_baseline = self.date_debut_prevue
        if self.date_fin_baseline is None and self.date_fin_prevue:
            self.date_fin_baseline = self.date_fin_prevue
        super().save(*args, **kwargs)

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
    # Le code d'un rôle (table `role`). **Propre à l'affectation** (décisions v1.2, §13bis) :
    # il prend par défaut le rôle du collaborateur sur la plateforme, mais peut différer d'un
    # projet à l'autre — conducteur de travaux ici, chef de chantier là.
    role_projet = models.CharField(
        _("rôle sur le projet"),
        max_length=50,
        default=RoleProjet.CHEF_PROJET,
        blank=True,
    )
    date_debut = models.DateField(_("date de début"), default=timezone.now)
    date_fin = models.DateField(_("date de fin"), null=True, blank=True)
    # Le périmètre : une ou plusieurs cases de l'arbre, et tout ce qui est en dessous. Aucune
    # case : tout le projet. Une permission s'exerce dans le périmètre (§13bis).
    perimetres = models.ManyToManyField(
        "projets.Element",
        blank=True,
        related_name="affectations_perimetre",
        db_table="affectation_projet_perimetre",
        verbose_name=_("périmètre"),
    )
    # Ce que fait un « autre membre » de l'encadrement, porté par le rôle consultant (VI).
    fonction_membre = models.CharField(
        _("fonction"),
        max_length=20,
        blank=True,
        default="",
        choices=[
            ("FINANCIER", _("Financier")),
            ("INGENIEUR", _("Ingénieur")),
            ("DOCUMENTALISTE", _("Documentaliste")),
            ("METREUR", _("Métreur")),
            ("QHSE", _("QHSE")),
            ("AUTRE", _("Autre")),
        ],
    )
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "affectation_projet"
        verbose_name = _("affectation au projet")
        verbose_name_plural = _("affectations aux projets")
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "projet"],
                name="uq_affectation_utilisateur_projet",
            ),
            # Règle fixée le 29/10/2026 : un seul chef de chantier par projet — c'est lui, et lui
            # seul, qui écrit le journal de chantier.
            models.UniqueConstraint(
                fields=["projet"],
                condition=models.Q(role_projet="CC", est_actif=True, supprime_le__isnull=True),
                name="uq_affectation_un_chef_chantier",
            ),
        ]

    def get_role_projet_display(self) -> str:
        """Le libellé du rôle, lu dans la table `role` ; à défaut celui de l'énumération."""
        from apps.accounts.models import Role

        role = Role.objects.filter(code__iexact=self.role_projet).only("libelle").first()
        if role:
            return role.libelle
        return dict(RoleProjet.choices).get(self.role_projet, self.role_projet)

    def __str__(self) -> str:
        return f"{self.utilisateur} sur {self.projet.nom} ({self.get_role_projet_display()})"
