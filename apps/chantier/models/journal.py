"""Complément du rapport historique pour le journal couvrant tout un chantier."""

from django.db import models

from apps.core.models import ModeleBase


class JournalChantier(ModeleBase):
    rapport = models.OneToOneField(
        "chantier.RapportJournalier", on_delete=models.RESTRICT, related_name="journal"
    )
    saisie = models.JSONField(default=dict)
    # Valeurs de référence au moment de la soumission, indépendantes du planning futur.
    photographie = models.JSONField(default=dict)
    valide_ct_par = models.ForeignKey(
        "accounts.Utilisateur",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="journaux_valides_ct",
    )
    valide_ct_le = models.DateTimeField(null=True, blank=True)
    commentaire_ct = models.TextField(blank=True)
    relance_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "journal_chantier"


class AlerteJournal(ModeleBase):
    """Notification interne persistante, dédupliquée par clé de formulaire."""

    journal = models.ForeignKey(JournalChantier, on_delete=models.RESTRICT, related_name="alertes")
    cle = models.CharField(max_length=100)
    type = models.CharField(max_length=30)
    description = models.TextField()
    destinataires = models.ManyToManyField("accounts.Utilisateur", related_name="alertes_journal")

    class Meta:
        db_table = "alerte_journal"
        constraints = [
            models.UniqueConstraint(fields=["journal", "cle"], name="uq_alerte_journal_cle")
        ]
