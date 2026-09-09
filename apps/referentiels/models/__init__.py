"""Application « referentiels » — schéma `public`.

Référentiels partagés par tous les tenants. Les dupliquer dans chaque schéma
garantirait qu'ils finissent désynchronisés.

Entités MCD : JourFerie  (MCD §4.7)
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

__all__ = ["JourFerie"]


class JourFerie(models.Model):
    """Calendrier des jours fériés, par pays.

    Alimente deux calculs qui, sans lui, seraient faux :
      · l'avancement théorique d'un projet (RG-12, US-047)
      · l'alerte de 17 h 30 sur les rapports manquants (US-057)
    """

    pays = models.CharField(_("pays"), max_length=2, default="CI", db_index=True)
    date_ferie = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=100)

    class Meta:
        db_table = "jour_ferie"
        verbose_name = _("jour férié")
        verbose_name_plural = _("jours fériés")
        ordering = ["date_ferie"]
        constraints = [models.UniqueConstraint(fields=["pays", "date_ferie"], name="uq_jour_ferie")]

    def __str__(self) -> str:
        return f"{self.date_ferie:%d/%m/%Y} — {self.libelle} ({self.pays})"
