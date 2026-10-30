"""Le découpage d'un projet en arbre — décisions v1.2 (schéma de l'entreprise).

**Un seul objet, l'élément** (§1). Phase, ouvrage, lot, activité sont le même objet ; ils ne
diffèrent que par leur parent. « Lot » n'est que le libellé du **niveau** où se trouve l'élément,
et aucun comportement ne dépend d'un libellé : ce qui varie dépend de la position (feuille ou
parent) ou d'un réglage explicite.

- **Le gabarit d'un projet** est la liste ordonnée de ses niveaux (`NiveauProjet`). Il est copié
  du modèle choisi à la création ; modifier le modèle ensuite ne change aucun projet (§3.11).
- **L'arbre se parcourt par chemin matérialisé** (`Element.chemin`) : la liste des identifiants
  des ancêtres puis de l'élément. Le sous-arbre se lit en une requête (`chemin__startswith`), les
  ancêtres en un découpage de chaîne, et le déplacement d'une branche réécrit les chemins de ses
  descendants en une mise à jour.
- **Listes et modèles de l'entreprise** : elle crée les siens et ajoute ses valeurs aux listes de
  la plateforme, qu'elle lit sans copie (`apps.catalogue.models.decoupage`).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.enums import StatutActivite
from apps.core.fields import MontantField, PourcentageField, QuantiteField
from apps.core.models import ModeleBase

__all__ = [
    "Element",
    "LigneModeleEntreprise",
    "ListeValeursEntreprise",
    "ModeMesure",
    "ModeleDecoupageEntreprise",
    "NiveauModeleEntreprise",
    "NiveauProjet",
    "ValeurListeEntreprise",
]


class ModeMesure(models.TextChoices):
    """Comment une feuille se mesure (§9, F3 formule 1)."""

    QUANTITE = "QUANTITE", _("Quantité")
    POURCENTAGE = "POURCENTAGE", _("Pourcentage déclaré")
    JALON = "JALON", _("Jalon (atteint / non atteint)")


# --------------------------------------------------------------------------
# Listes de valeurs de l'entreprise (§4)
# --------------------------------------------------------------------------
class ListeValeursEntreprise(ModeleBase):
    libelle = models.CharField(_("libellé"), max_length=100)
    description = models.TextField(_("description"), blank=True, default="")
    ordre = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        db_table = "liste_valeurs_entreprise"
        ordering = ["ordre", "libelle"]

    def __str__(self) -> str:
        return self.libelle


class ValeurListeEntreprise(ModeleBase):
    """Une valeur ajoutée par l'entreprise — à l'une de ses listes, ou à une liste plateforme."""

    liste_entreprise = models.ForeignKey(
        ListeValeursEntreprise,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="valeurs",
    )
    liste_plateforme = models.ForeignKey(
        "catalogue.ListeValeursPlateforme",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="valeurs_entreprises",
    )
    libelle = models.CharField(_("libellé"), max_length=200)
    groupe = models.CharField(_("groupe"), max_length=100, blank=True, default="")
    cle_comparaison = models.CharField(max_length=200, editable=False, default="")
    ordre = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        db_table = "valeur_liste_entreprise"
        ordering = ["ordre", "libelle"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(liste_entreprise__isnull=False, liste_plateforme__isnull=True)
                    | models.Q(liste_entreprise__isnull=True, liste_plateforme__isnull=False)
                ),
                name="chk_valeur_liste_une_liste",
            ),
            models.UniqueConstraint(
                fields=["liste_entreprise", "cle_comparaison"],
                condition=models.Q(supprime_le__isnull=True, liste_entreprise__isnull=False),
                name="uq_valeur_liste_entreprise_cle",
            ),
            models.UniqueConstraint(
                fields=["liste_plateforme", "cle_comparaison"],
                condition=models.Q(supprime_le__isnull=True, liste_plateforme__isnull=False),
                name="uq_valeur_liste_plateforme_ajoutee_cle",
            ),
        ]

    def save(self, *args, **kwargs):
        self.cle_comparaison = cle_comparaison(self.libelle)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.libelle


# --------------------------------------------------------------------------
# Modèles de découpage de l'entreprise (§3)
# --------------------------------------------------------------------------
class ModeleDecoupageEntreprise(ModeleBase):
    nom = models.CharField(_("nom"), max_length=150)
    description = models.TextField(_("description"), blank=True, default="")
    types_projet = models.JSONField(_("types de projet"), default=list, blank=True)
    # Pour ces types, ce modèle pré-remplit le tableau à la place du modèle plateforme.
    par_defaut_pour = models.JSONField(_("modèle par défaut pour"), default=list, blank=True)
    # Une copie personnalisée d'un modèle plateforme reste liée à son original par identifiant
    # (jamais par son nom) et retient la version copiée, pour signaler qu'il a changé depuis.
    origine = models.ForeignKey(
        "catalogue.ModeleDecoupagePlateforme",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copies_entreprise",
    )
    version_origine = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "modele_decoupage_entreprise"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom


class NiveauModeleEntreprise(ModeleBase):
    modele = models.ForeignKey(
        ModeleDecoupageEntreprise, on_delete=models.CASCADE, related_name="niveaux"
    )
    ordre = models.PositiveSmallIntegerField(_("ordre"))
    libelle = models.CharField(_("libellé"), max_length=60)
    liste_plateforme = models.ForeignKey(
        "catalogue.ListeValeursPlateforme",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="niveaux_modeles_entreprise",
    )
    liste_entreprise = models.ForeignKey(
        ListeValeursEntreprise,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="niveaux_modeles",
    )
    alerter = models.BooleanField(_("alerter à ce niveau"), default=False)

    class Meta:
        db_table = "niveau_modele_entreprise"
        ordering = ["modele", "ordre"]


class LigneModeleEntreprise(ModeleBase):
    modele = models.ForeignKey(
        ModeleDecoupageEntreprise, on_delete=models.CASCADE, related_name="lignes"
    )
    ordre = models.PositiveIntegerField(_("ordre"), default=0)
    valeurs = models.JSONField(_("valeurs"), default=list)

    class Meta:
        db_table = "ligne_modele_entreprise"
        ordering = ["modele", "ordre"]


# --------------------------------------------------------------------------
# Le gabarit et l'arbre d'un projet (§1, §2, §7)
# --------------------------------------------------------------------------
class NiveauProjet(ModeleBase):
    projet = models.ForeignKey("projets.Projet", on_delete=models.CASCADE, related_name="niveaux")
    ordre = models.PositiveSmallIntegerField(_("ordre"))
    libelle = models.CharField(_("libellé"), max_length=60)
    liste_plateforme = models.ForeignKey(
        "catalogue.ListeValeursPlateforme",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="niveaux_projets",
    )
    liste_entreprise = models.ForeignKey(
        ListeValeursEntreprise,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="niveaux_projets",
    )
    alerter = models.BooleanField(_("alerter à ce niveau"), default=False)

    class Meta:
        db_table = "niveau_projet"
        ordering = ["projet", "ordre"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "ordre"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_niveau_projet_ordre",
            )
        ]

    def __str__(self) -> str:
        return f"{self.ordre}. {self.libelle}"


class Element(ModeleBase):
    """Un élément de découpage : une case de l'arbre du projet.

    Une **feuille** est un élément sans enfant actif ; ce statut n'est pas fixe (découper une
    feuille en fait un parent). La mesure ne se saisit que sur les feuilles ; un parent porte une
    enveloppe facultative, ses dates et sa baseline, et voit son avancement calculé (§7 à §9).
    """

    projet = models.ForeignKey("projets.Projet", on_delete=models.CASCADE, related_name="elements")
    parent = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="enfants",
    )
    niveau = models.ForeignKey(NiveauProjet, on_delete=models.PROTECT, related_name="elements")
    libelle = models.CharField(_("intitulé"), max_length=200)
    cle_comparaison = models.CharField(max_length=200, editable=False, default="")
    # Code libre facultatif, pour reprendre la numérotation du bordereau du client (A-4).
    code = models.CharField(_("code libre"), max_length=30, blank=True, default="")
    ordre = models.IntegerField(_("ordre"), default=0)
    # Identifiants des ancêtres puis de l'élément, séparés par « / » et terminés par « / ».
    chemin = models.CharField(max_length=2000, db_index=True, editable=False, default="")
    profondeur = models.PositiveSmallIntegerField(default=0, editable=False)
    motif = models.TextField(_("motif"), blank=True, default="")

    # --- Mesure (feuilles) ---------------------------------------------------------------------
    mode_mesure = models.CharField(
        _("mode de mesure"), max_length=20, choices=ModeMesure.choices, default=ModeMesure.QUANTITE
    )
    unite = models.CharField(_("unité"), max_length=10, blank=True, default="")
    # Initiale : jamais modifiée ; prévue : la quantité courante, sur laquelle se mesure le réalisé.
    quantite_initiale = QuantiteField(_("quantité initiale"), null=True, blank=True)
    quantite_prevue = QuantiteField(_("quantité prévue"), null=True, blank=True)
    quantite_realisee = QuantiteField(_("quantité réalisée"), default=0)
    pourcentage_declare = PourcentageField(_("pourcentage déclaré"), null=True, blank=True)
    # Physique calculé (F3), stocké pour les listes ; nul quand il est indisponible.
    avancement = PourcentageField(_("avancement physique (%)"), null=True, blank=True)

    # --- Montants (§8) -------------------------------------------------------------------------
    montant_initial = MontantField(_("montant initial (centimes)"), null=True, blank=True)
    montant = MontantField(_("montant courant (centimes)"), null=True, blank=True)
    enveloppe = MontantField(_("enveloppe (centimes)"), null=True, blank=True)

    # --- Dates (§11) : chaque élément a les siennes, parents compris -------------------------
    date_debut_prevue = models.DateField(_("début prévu"), null=True, blank=True)
    date_fin_prevue = models.DateField(_("fin prévue"), null=True, blank=True)
    date_debut_baseline = models.DateField(_("début baseline v0"), null=True, blank=True)
    date_fin_baseline = models.DateField(_("fin baseline v0"), null=True, blank=True)
    date_debut_reelle = models.DateField(_("début réel"), null=True, blank=True)
    date_fin_reelle = models.DateField(_("fin réelle"), null=True, blank=True)
    # Jours accordés par les avenants qui citent cette case (30/10/2026).
    jours_accordes = models.IntegerField(_("jours accordés par avenant"), default=0)

    # --- Exécution : définie sur n'importe quel élément, héritée par ses descendants --------
    mode_execution = models.CharField(_("mode d'exécution"), max_length=60, blank=True, default="")
    type_bordereau = models.CharField(_("type de bordereau"), max_length=20, blank=True, default="")
    titulaire = models.ForeignKey(
        "tiers.Tiers",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="elements_titulaire",
    )

    # --- État (§10) --------------------------------------------------------------------------
    statut = models.TextField(_("statut"), default=StatutActivite.PLANIFIE)
    cloture = models.BooleanField(_("clôturé"), default=False)
    cloture_le = models.DateTimeField(null=True, blank=True)
    suspendu = models.BooleanField(_("suspendu"), default=False)
    est_actif = models.BooleanField(_("est actif"), default=True)

    class Meta:
        db_table = "element"
        verbose_name = _("élément de découpage")
        verbose_name_plural = _("éléments de découpage")
        ordering = ["projet", "profondeur", "ordre", "cree_le"]
        indexes = [models.Index(fields=["projet", "parent"], name="idx_element_projet_parent")]
        constraints = [
            # A-6 : deux frères ne portent pas le même intitulé (sans accents, casse ni espaces).
            models.UniqueConstraint(
                fields=["parent", "cle_comparaison"],
                condition=models.Q(supprime_le__isnull=True, parent__isnull=False),
                name="uq_element_frere_intitule",
            ),
            models.UniqueConstraint(
                fields=["projet", "cle_comparaison"],
                condition=models.Q(supprime_le__isnull=True, parent__isnull=True),
                name="uq_element_racine_intitule",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(date_debut_prevue__isnull=True)
                    | models.Q(date_fin_prevue__isnull=True)
                    | models.Q(date_fin_prevue__gte=models.F("date_debut_prevue"))
                ),
                name="chk_element_dates_coherentes",
            ),
        ]

    def save(self, *args, **kwargs):
        self.cle_comparaison = cle_comparaison(self.libelle)
        # La baseline v0 se pose à la première saisie des dates et ne bouge plus (§11).
        if self.date_debut_baseline is None and self.date_debut_prevue:
            self.date_debut_baseline = self.date_debut_prevue
        if self.date_fin_baseline is None and self.date_fin_prevue:
            self.date_fin_baseline = self.date_fin_prevue
        if self.quantite_initiale is None and self.quantite_prevue is not None:
            self.quantite_initiale = self.quantite_prevue
        if self.montant_initial is None and self.montant is not None:
            self.montant_initial = self.montant
        prefixe = self.parent.chemin if self.parent_id else ""
        self.chemin = f"{prefixe}{self.pk}/"
        self.profondeur = prefixe.count("/")
        super().save(*args, **kwargs)

    @property
    def date_fin_contractuelle(self):
        """L'origine (baseline v0) plus les jours accordés par avenant."""
        from datetime import timedelta

        if not self.date_fin_baseline:
            return None
        return self.date_fin_baseline + timedelta(days=self.jours_accordes or 0)

    @property
    def ancetres_ids(self) -> list[str]:
        """Identifiants des ancêtres, du plus haut au parent direct."""
        return [i for i in self.chemin.split("/") if i][:-1]

    def __str__(self) -> str:
        return self.libelle
