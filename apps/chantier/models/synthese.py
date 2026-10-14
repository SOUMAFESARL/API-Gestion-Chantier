"""La synthèse périodique d'un chantier : ce qu'en dit le CT, et qui l'a signée."""

from django.db import models

from apps.core.models import ModeleBase


class SynthesePeriodique(ModeleBase):
    """La part écrite et signée d'une synthèse — les chiffres, eux, se calculent.

    Une synthèse n'existe en base qu'à partir du moment où le conducteur de
    travaux y écrit : avant, elle se calcule à la demande des rapports de la
    période (`selectors/synthese.py`), et rien n'est à conserver.

    **À la signature du CT, le calcul est figé** dans `photographie` : ce qui a
    été signé ne bouge plus, même si un rapport de la période est approuvé ou
    rejeté ensuite — comme `JournalChantier.photographie` pour un rapport.

    Seules les **semaines et les mois clos** passent par le circuit : une
    période personnalisée se consulte, elle ne se signe pas (décision du
    14/10/2026).
    """

    class Type(models.TextChoices):
        HEBDOMADAIRE = "HEBDOMADAIRE", "Hebdomadaire"
        MENSUELLE = "MENSUELLE", "Mensuelle"

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "En rédaction par le CT"
        SOUMISE = "SOUMISE", "Signée par le CT, en attente du CP"
        APPROUVEE = "APPROUVEE", "Approuvée par le CP"
        REJETEE = "REJETEE", "Rejetée par le CP, rendue au CT"

    projet = models.ForeignKey(
        "projets.Projet", on_delete=models.RESTRICT, related_name="syntheses_periodiques"
    )
    type = models.CharField(max_length=12, choices=Type.choices)
    date_debut = models.DateField()
    date_fin = models.DateField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)

    appreciation = models.TextField(blank=True)
    #: `[{lot_code, activite, objectif, cible, prerequis}]` — la période suivante.
    objectifs = models.JSONField(default=list)
    redigee_par = models.ForeignKey(
        "accounts.Utilisateur",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="syntheses_redigees",
    )
    redigee_le = models.DateTimeField(null=True, blank=True)

    #: Le calcul tel que le CT l'a signé ; vide tant qu'il n'a pas signé.
    photographie = models.JSONField(default=dict)
    signee_ct_par = models.ForeignKey(
        "accounts.Utilisateur",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="syntheses_signees_ct",
    )
    signee_ct_le = models.DateTimeField(null=True, blank=True)

    #: Le CP qui a approuvé ou rejeté, et son commentaire ou son motif.
    decidee_cp_par = models.ForeignKey(
        "accounts.Utilisateur",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="syntheses_decidees_cp",
    )
    decidee_cp_le = models.DateTimeField(null=True, blank=True)
    commentaire_cp = models.TextField(blank=True)

    class Meta:
        db_table = "synthese_periodique"
        ordering = ["-date_debut"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "type", "date_debut", "date_fin"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_synthese_projet_periode",
            ),
            models.CheckConstraint(
                condition=models.Q(date_fin__gte=models.F("date_debut")),
                name="ck_synthese_periode_ordonnee",
            ),
        ]

    def __str__(self) -> str:
        return f"Synthèse {self.type} {self.date_debut} → {self.date_fin} ({self.statut})"
