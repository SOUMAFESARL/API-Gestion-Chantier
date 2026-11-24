"""Modèles principaux pour l'application projets — MLD §6.1 et §6.4.

Tables d'entreprise (`ModeleEntreprise`).
"""

from pathlib import Path

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import BadgeSante, NatureProjet, RoleProjet, StatutProjet, TypeProjet
from apps.core.models import ModeleEntreprise
from apps.entreprises.selectors import slug_courant
from apps.projets.storage import StockageContrats

__all__ = ["AffectationProjet", "Projet", "chemin_ordre_service_projet", "libelles_des_roles"]


def chemin_ordre_service_projet(instance, filename):
    extension = Path(filename).suffix.lower()
    if extension == ".jepg":
        extension = ".jpeg"
    return (
        f"{slug_courant() or 'plateforme'}/projets/{instance.pk}/"
        f"ordre-service/{instance.pk}{extension}"
    )


def libelles_des_roles() -> dict[str, str]:
    """Code du rôle (en majuscules) vers son libellé, en une requête.

    Même résultat que la lecture rôle par rôle de `get_role_projet_display` : à code égal sans
    tenir compte de la casse, le premier dans l'ordre de la table l'emporte.
    """
    from apps.accounts.models import Role

    libelles: dict[str, str] = {}
    for code, libelle in Role.objects.values_list("code", "libelle"):
        libelles.setdefault((code or "").upper(), libelle)
    return libelles


class Projet(ModeleEntreprise):
    """Chantier / Projet de construction."""

    reference = models.CharField(_("référence"), max_length=30)
    nom = models.CharField(_("nom"), max_length=200)
    nature_projet = models.CharField(
        _("type de projet"),
        max_length=10,
        choices=NatureProjet.choices,
        blank=True,
        default="",
        db_index=True,
    )
    # Code d'une entrée des référentiels (plateforme ou entreprise) — plus de liste figée.
    type_projet = models.CharField(
        _("catégorie d'ouvrage"),
        max_length=60,
        default=TypeProjet.BATIMENT_RESIDENTIEL,
    )
    description = models.TextField(_("description"), blank=True)
    informations_complementaires = models.JSONField(
        _("informations complémentaires"),
        default=dict,
        blank=True,
    )

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
        _("budget prévisionnel (centimes)"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Budget prévisionnel interne en centimes de FCFA. Facultatif et modifiable."),
    )
    budget_contractuel_initial = models.BigIntegerField(
        _("budget contractuel initial (centimes)"),
        null=True,
        blank=True,
        default=None,
        help_text=_(
            "Montant contractuel initial en centimes de FCFA. "
            "Exige un contrat joint et devient immuable après pose."
        ),
    )
    duree_contractuelle_annees = models.PositiveIntegerField(
        _("durée contractuelle (années)"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Nombre d'années de la durée contractuelle d'exécution (exige un contrat)."),
    )
    duree_contractuelle_mois = models.PositiveIntegerField(
        _("durée contractuelle (mois)"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Nombre de mois de la durée contractuelle d'exécution (exige un contrat)."),
    )
    duree_contractuelle_jours = models.PositiveIntegerField(
        _("durée contractuelle (jours)"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Nombre de jours de la durée contractuelle d'exécution (exige un contrat)."),
    )
    date_debut_contractuelle = models.DateField(
        _("date de début contractuelle"),
        null=True,
        blank=True,
        default=None,
        help_text=_(
            "Date d'effet de l'ordre de service de démarrage. "
            "Exige un fichier OS ; modifiable uniquement via un nouvel OS."
        ),
    )

    date_debut_prevue = models.DateField(_("date de début prévue"), null=True, blank=True)
    date_fin_prevue = models.DateField(_("date de fin prévue"), null=True, blank=True)

    date_debut_baseline = models.DateField(
        _("date de début baseline v0"),
        null=True,
        blank=True,
        help_text=_("Date de début prévisionnelle initiale (figée, intacte)."),
    )
    date_fin_baseline = models.DateField(
        _("date de fin baseline v0"),
        null=True,
        blank=True,
        help_text=_("Date de fin prévisionnelle initiale (figée, intacte)."),
    )

    date_debut_reelle = models.DateField(_("date de début réelle"), null=True, blank=True)
    date_fin_reelle = models.DateField(_("date de fin réelle"), null=True, blank=True)

    # Cumuls des avenants portant sur le projet entier, tenus par `services.avenants` :
    # évite tout N+1 pour le calcul de `date_fin_contractuelle` et `budget_contractuel`.
    jours_accordes = models.IntegerField(_("jours accordés par avenant"), default=0)
    prolongation_annees = models.PositiveIntegerField(
        _("années accordées par avenant"), default=0
    )
    prolongation_mois = models.PositiveIntegerField(_("mois accordés par avenant"), default=0)
    prolongation_jours = models.PositiveIntegerField(
        _("jours accordés par avenant (cumul)"), default=0
    )
    montant_avenants = models.BigIntegerField(_("montant des avenants"), default=0)

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

    ordre_service = models.FileField(
        _("ordre de service de démarrage"),
        upload_to=chemin_ordre_service_projet,
        storage=StockageContrats(),
        max_length=255,
        blank=True,
    )
    ordre_service_nom = models.CharField(
        _("nom de l'ordre de service"),
        max_length=255,
        blank=True,
    )
    ordre_service_taille = models.PositiveBigIntegerField(
        _("taille de l'ordre de service"),
        null=True,
        blank=True,
    )
    ordre_service_type = models.CharField(
        _("type MIME de l'ordre de service"),
        max_length=50,
        blank=True,
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
                fields=["entreprise", "reference"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_projet_reference",
            ),
            # Cible des clés composites (projet_id, entreprise_id) des tables enfants (D9, R-3) :
            # un enfant ne peut pas pointer vers le projet d'une autre entreprise.
            models.UniqueConstraint(fields=["id", "entreprise"], name="uq_projet_id_entreprise"),
            models.CheckConstraint(
                condition=models.Q(budget_contractuel_initial__isnull=True)
                | models.Q(budget_contractuel_initial__gte=0),
                name="chk_projet_budget_contractuel_positif",
            ),
        ]

    @property
    def a_duree_contractuelle(self) -> bool:
        """Vrai dès que la durée contractuelle d'exécution est posée (> 0)."""
        return (
            (self.duree_contractuelle_annees or 0)
            + (self.duree_contractuelle_mois or 0)
            + (self.duree_contractuelle_jours or 0)
        ) > 0

    @property
    def duree_contractuelle(self) -> dict[str, int] | None:
        """Durée contractuelle initiale du marché (années, mois, jours), ou None."""
        if not self.a_duree_contractuelle:
            return None
        return {
            "annees": self.duree_contractuelle_annees or 0,
            "mois": self.duree_contractuelle_mois or 0,
            "jours": self.duree_contractuelle_jours or 0,
        }

    @property
    def prolongation_contractuelle(self) -> dict[str, int]:
        """Cumul des prolongations accordées par avenant sur le projet entier."""
        return {
            "annees": self.prolongation_annees or 0,
            "mois": self.prolongation_mois or 0,
            "jours": self.prolongation_jours or 0,
        }

    @property
    def date_fin_contractuelle_initiale(self):
        """Date de début contractuelle (OS) + durée contractuelle initiale, sans avenants."""
        if not self.date_debut_contractuelle or not self.a_duree_contractuelle:
            return None
        from apps.projets.services.durees import ajouter_duree_calendaire

        return ajouter_duree_calendaire(
            self.date_debut_contractuelle,
            annees=self.duree_contractuelle_annees or 0,
            mois=self.duree_contractuelle_mois or 0,
            jours=self.duree_contractuelle_jours or 0,
        )

    @property
    def date_fin_contractuelle(self):
        """Début contractuel (OS) + durée contractuelle + prolongations d'avenants.

        Reste None tant que l'OS de démarrage ou la durée contractuelle manque.
        """
        if not self.date_debut_contractuelle or not self.a_duree_contractuelle:
            return None
        from apps.projets.services.durees import ajouter_duree_calendaire

        return ajouter_duree_calendaire(
            self.date_debut_contractuelle,
            annees=(self.duree_contractuelle_annees or 0) + (self.prolongation_annees or 0),
            mois=(self.duree_contractuelle_mois or 0) + (self.prolongation_mois or 0),
            jours=(self.duree_contractuelle_jours or 0) + (self.prolongation_jours or 0),
        )

    @property
    def budget_contractuel(self):
        """Budget contractuel en vigueur (initial + avenants), ou None sans contrat chiffré."""
        if self.budget_contractuel_initial is None:
            return None
        return self.budget_contractuel_initial + (self.montant_avenants or 0)

    @property
    def budget_reference(self):
        """Plafond d'alerte du découpage : contractuel s'il existe, sinon prévisionnel."""
        if self.budget_contractuel is not None:
            return self.budget_contractuel
        return self.budget_initial_montant

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


class AffectationProjet(ModeleEntreprise):
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
            # L'unicité d'un rôle sur le projet est un réglage du rôle (`Role.unique_par_projet`,
            # 30/10/2026), vérifiée par le service des affectations.
        ]

    def get_role_projet_display(self, libelles: dict[str, str] | None = None) -> str:
        """Le libellé du rôle, lu dans la table `role` ; à défaut le rôle de l'utilisateur
        dans l'entreprise ou l'énumération. Ne renvoie jamais un libellé générique « Autre ».

        `libelles` (voir `libelles_des_roles`) évite une requête par affectation quand on en
        affiche plusieurs.
        """
        code = (self.role_projet or "").strip().upper()
        if code and code not in ("AUTRE", "AUTRE_MEMBRE"):
            if libelles is not None:
                libelle = libelles.get(code)
            else:
                from apps.accounts.models import Role

                role = Role.objects.filter(code__iexact=code).only("libelle").first()
                libelle = role.libelle if role else None
            if libelle:
                return libelle
            enum_label = dict(RoleProjet.choices).get(code)
            if enum_label:
                return enum_label
            return code
        if self.utilisateur_id:
            from apps.projets.selectors.encadrement import role_entreprise_utilisateur

            _code_ent, libelle_ent = role_entreprise_utilisateur(self.utilisateur, libelles)
            if libelle_ent:
                return libelle_ent
        return ""

    def __str__(self) -> str:
        return f"{self.utilisateur} sur {self.projet.nom} ({self.get_role_projet_display()})"
