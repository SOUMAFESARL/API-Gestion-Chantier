"""Modèle JournalPlateforme — MLD §4.6.

Journal immuable à insertion seule retraçant toutes les actions effectuées par
le personnel de l'éditeur sur la plateforme et les tenants clients (dont les
sessions d'assistance en direct / impersonifications).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

__all__ = ["JournalPlateforme"]


class JournalPlateforme(models.Model):
    """Journal d'audit plateforme — schéma `public` (MLD §4.6).

    Trace toutes les opérations de support, d'impersonification et
    d'administration de la plateforme CCD Digital.
    """

    id = models.BigAutoField(primary_key=True)

    # Identifiant du super admin ou membre du support (dans public.utilisateur)
    utilisateur_id = models.UUIDField(
        _("utilisateur plateforme"), null=True, blank=True, db_index=True
    )

    # Identifiant de l'entreprise cliente concernée (dans public.entreprise_cliente)
    entreprise_id = models.UUIDField(_("entreprise"), null=True, blank=True, db_index=True)

    action = models.CharField(_("action"), max_length=50, db_index=True)
    detail = models.JSONField(_("détails"), null=True, blank=True)

    adresse_ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    appareil = models.CharField(_("appareil"), max_length=255, blank=True)
    horodatage = models.DateTimeField(_("horodatage"), auto_now_add=True, db_index=True)

    class Meta:
        db_table = "journal_plateforme"
        verbose_name = _("entrée du journal plateforme")
        verbose_name_plural = _("journal plateforme")
        ordering = ["-horodatage"]
        indexes = [
            models.Index(fields=["entreprise_id", "-horodatage"], name="plat_audit_entr_idx"),
            models.Index(fields=["utilisateur_id", "-horodatage"], name="plat_audit_user_idx"),
            models.Index(fields=["action", "-horodatage"], name="plat_audit_act_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.horodatage:%Y-%m-%d %H:%M} — {self.action} (entreprise={self.entreprise_id})"
