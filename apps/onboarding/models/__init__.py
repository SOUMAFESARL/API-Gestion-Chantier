"""Application « onboarding » — la configuration initiale d'une entreprise.

Entités : ProgressionConfiguration, EtapeConfiguration  ·  contrat T-024

**`TENANT_APPS`, et l'argument n'est pas la commodité.** La progression est lue
**à chaque affichage du tableau de bord**, par chaque utilisateur, pour décider
d'afficher ou non « Configuration 67 % — reprendre ». La placer dans `public`
ferait de la table de la plateforme une dépendance de chaque page de chaque
client — exactement ce que le découpage par schéma existe pour éviter.

L'agrégat de l'éditeur — « combien de clients ont fini ? » — reste possible par
un parcours nocturne des schémas. Le produit en fait déjà un pour l'extraction
anonymisée du service ML ; un second passage sur la même boucle ne coûte rien,
et un tableau de bord commercial supporte le décalage d'une nuit.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CodeEtape, ModeEtape, StatutConfiguration
from apps.core.models import ModeleBase

__all__ = [
    "ETAPES",
    "ETAPES_FACULTATIVES",
    "CodeEtape",
    "EtapeConfiguration",
    "ProgressionConfiguration",
]

# **Les trois énumérations vivent dans `apps.core.enums`, pas ici.** C'est ce
# qui les met sur le fil : `GET /api/v1/referentiels/enumerations/` construit sa
# table par introspection de ce module, et le contrat T-024 §2.1 veut que les
# libellés des étapes viennent de là — jamais du code de l'écran.

# **L'ordre est porté par le code, pas par la base.** Trois étapes fixes que
# personne ne modifiera : une table de référence serait une jointure de plus à
# chaque appel, pour trois lignes.
ETAPES: tuple[str, ...] = (
    CodeEtape.ENTREPRISE,
    CodeEtape.PROJET,
    CodeEtape.EQUIPE,
)

# `PROJET` et `EQUIPE` peuvent être passées (US-019 / Refonte Sprint 1).
# Une entreprise sans projet initial arrive sur le tableau de bord à vide
# avec la modale de création de premier chantier.
ETAPES_FACULTATIVES: frozenset[str] = frozenset({CodeEtape.PROJET, CodeEtape.EQUIPE})


class ProgressionConfiguration(ModeleBase):
    """Où en est la configuration — **une seule ligne par schéma**.

    **La configuration appartient à l'entreprise, pas à la personne.** Un second
    administrateur ne la recommence pas ; il la reprend.

    Le couple `UNIQUE` + `CHECK` sur une colonne toujours vraie est le seul
    moyen de dire « une seule ligne » à PostgreSQL : l'unicité seule
    autoriserait une seconde ligne à `false`, la vérification seule
    n'empêcherait pas deux lignes à `true`. Ensemble, elles rendent la seconde
    insertion impossible — **par la base, pas par un contrôle applicatif qu'un
    script d'administration contournerait sans le savoir**.

    **Aucune colonne de brouillon.** La saisie en cours vit dans le
    `sessionStorage` du navigateur. Une colonne `donnees_brouillon` créerait un
    état que chaque liste, chaque compteur et chaque export devrait apprendre à
    ignorer — et il s'en trouverait toujours un pour l'oublier.
    """

    Statut = StatutConfiguration

    unique_par_schema = models.BooleanField(default=True, editable=False)

    statut = models.CharField(
        _("statut"), max_length=20, choices=Statut.choices, default=Statut.EN_COURS
    )
    etape_courante = models.CharField(
        _("étape courante"),
        max_length=20,
        choices=CodeEtape.choices,
        default=CodeEtape.ENTREPRISE,
    )
    demarre_le = models.DateTimeField(_("démarrée le"), auto_now_add=True)
    terminee_le = models.DateTimeField(_("terminée le"), null=True, blank=True)

    class Meta:
        db_table = "progression_configuration"
        verbose_name = _("progression de configuration")
        verbose_name_plural = _("progressions de configuration")
        constraints = [
            models.UniqueConstraint(fields=["unique_par_schema"], name="uq_progression_singleton"),
            models.CheckConstraint(
                condition=models.Q(unique_par_schema=True),
                name="chk_progression_singleton",
            ),
        ]

    def __str__(self) -> str:
        return f"Configuration — {self.get_statut_display()} ({self.pourcentage} %)"

    @property
    def pourcentage(self) -> int:
        """Étapes franchies sur étapes totales. **Jamais stocké.**

        **0 % à l'ouverture, et non 33 %.** M9 affichait 33 % pour quelqu'un qui
        n'a rien validé : c'est la position, pas l'avancement — et « Étape 1
        sur 3 » dit déjà la position.

        L'arrondi est à l'entier : 33 et 67, jamais 33,33. Un pourcentage de
        configuration n'a pas de décimale à défendre.
        """
        if self.terminee_le is not None:
            return 100
        return round(100 * self.etapes.count() / len(ETAPES))

    @property
    def est_terminee(self) -> bool:
        """**L'état final est un fait daté, pas un calcul permanent.**

        Le jour où une quatrième étape s'ajoute, une entreprise déjà terminée ne
        repasse pas à 75 % : `terminee_le` est non nul, et c'est la seule
        question posée. Sans cette règle, la livraison de l'étape rouvrirait le
        wizard chez tous les clients existants, un lundi matin, sans que
        personne ne l'ait demandé.
        """
        return self.terminee_le is not None


class EtapeConfiguration(ModeleBase):
    """Une étape franchie — **une ligne, jamais plus**.

    Une table fille plutôt qu'un tableau JSONB, et le motif est la concurrence :
    un tableau oblige à lire avant d'écrire, et c'est là que deux
    administrateurs se marchent dessus. L'`INSERT` n'a rien à lire — il réussit,
    ou il heurte l'unicité. **Dans les deux cas le résultat est celui d'un geste
    fait une fois** : de l'idempotence obtenue par la base, pas par une
    précaution dans un service.

    Elle porte en plus ce qu'un tableau ne saurait dire : *quand*, et *qui* —
    Socle §2.4.
    """

    Mode = ModeEtape

    progression = models.ForeignKey(
        ProgressionConfiguration, on_delete=models.CASCADE, related_name="etapes"
    )
    code = models.CharField(_("code"), max_length=20, choices=CodeEtape.choices)
    mode = models.CharField(_("mode"), max_length=10, choices=Mode.choices)
    franchie_le = models.DateTimeField(_("franchie le"), auto_now_add=True)
    franchie_par = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.RESTRICT,
        related_name="etapes_franchies",
    )

    class Meta:
        db_table = "etape_configuration"
        verbose_name = _("étape de configuration")
        verbose_name_plural = _("étapes de configuration")
        ordering = ["franchie_le"]
        constraints = [
            models.UniqueConstraint(fields=["progression", "code"], name="uq_etape_configuration")
        ]

    def __str__(self) -> str:
        return f"{self.get_code_display()} — {self.get_mode_display()}"
