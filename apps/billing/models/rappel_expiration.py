"""Trace d'envoi par destinataire, echeance et seuil de rappel."""

from django.db import models

from apps.core.models import ModeleBase


class RappelExpiration(ModeleBase):
    abonnement = models.ForeignKey("billing.Abonnement", on_delete=models.CASCADE)
    date_echeance = models.DateField()
    seuil = models.PositiveSmallIntegerField(choices=[(j, str(j)) for j in (7, 3, 1, 0)])
    destinataire = models.EmailField()
    envoye_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rappel_expiration_abonnement"
        constraints = [
            models.UniqueConstraint(
                fields=["abonnement", "date_echeance", "seuil", "destinataire"],
                name="uq_rappel_expiration_destinataire",
            ),
        ]
