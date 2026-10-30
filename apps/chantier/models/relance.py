"""La relance d'une ligne du journal : un rapport attendu, ou une signature attendue."""

from django.db import models

from apps.core.models import ModeleBase


class RelanceJournal(ModeleBase):
    """Une relance envoyée par e-mail, pour une ligne du journal (un chantier, un rédacteur, un jour).

    Une ligne du journal n'a pas toujours de rapport : quand il manque, il
    n'existe ni `RapportJournalier` ni `JournalChantier` où noter qu'on l'a
    réclamé. La relance se rattache donc au chantier et au jour du rapport,
    et au rapport seulement s'il existe.

    **Une relance par ligne et par jour** (décision du 14/10/2026) : la
    contrainte porte sur le jour d'envoi, pour qu'une ligne restée en souffrance
    puisse être relancée de nouveau le lendemain, jamais deux fois le même jour.
    """

    class Etape(models.TextChoices):
        # Les codes des étapes restent CC / CT / CP ; elles vont à ceux qui ont la permission
        # de rédiger, de valider, d'approuver (30/10/2026), quel que soit le nom de leur rôle.
        CHEF_CHANTIER = "CC", "Rédaction"
        CONDUCTEUR_TRAVAUX = "CT", "Validation"
        CHEF_PROJET = "CP", "Approbation"

    projet = models.ForeignKey(
        "projets.Projet", on_delete=models.RESTRICT, related_name="relances_journal"
    )
    date_rapport = models.DateField()
    #: Le rédacteur dont le rapport est attendu ; vide sur un chantier sans rédacteur affecté.
    redacteur = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="relances_journal_redacteur",
    )
    #: Le jour d'envoi, à l'heure locale du chantier.
    jour = models.DateField()
    journal = models.ForeignKey(
        "chantier.JournalChantier",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="relances",
    )
    etape = models.CharField(max_length=2, choices=Etape.choices)
    destinataires = models.ManyToManyField(
        "accounts.Utilisateur", related_name="relances_journal_recues"
    )
    #: Envoyée par la tâche de 17 h 30, et non par une personne (`cree_par` est alors vide).
    automatique = models.BooleanField(default=False)

    class Meta:
        db_table = "relance_journal"
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "redacteur", "date_rapport", "jour"],
                condition=models.Q(supprime_le__isnull=True, redacteur__isnull=False),
                name="uq_relance_journal_ligne_jour",
            ),
            models.UniqueConstraint(
                fields=["projet", "date_rapport", "jour"],
                condition=models.Q(supprime_le__isnull=True, redacteur__isnull=True),
                name="uq_relance_journal_ligne_anonyme_jour",
            ),
        ]
