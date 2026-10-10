"""Messagerie de la plateforme : le serveur SMTP par lequel partent tous les e-mails du produit.

Schéma : public. Une seule ligne existe (clé 1) : c'est un réglage, pas une collection.

**Pourquoi en base et pas seulement dans le `.env`.** Le `.env` du serveur n'est modifiable que
depuis le panneau d'hébergement ; un mot de passe d'application révoqué (par exemple quand la
validation en deux étapes du compte Google est supprimée) rendait tout envoi muet, sans que le
superviseur puisse le corriger. Le réglage saisi ici l'emporte sur le `.env`, qui reste le repli.

Le mot de passe n'est **jamais** stocké en clair ni renvoyé par l'API : voir
`services/messagerie.py` (chiffrement authentifié, clé dérivée de `SECRET_KEY`).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ParametresMessagerie(models.Model):
    """Réglage unique : le serveur SMTP et l'expéditeur de la plateforme."""

    class Chiffrement(models.TextChoices):
        STARTTLS = "STARTTLS", _("STARTTLS (port 587)")
        SSL = "SSL", _("SSL/TLS (port 465)")
        AUCUN = "AUCUN", _("Aucun")

    hote = models.CharField(_("serveur SMTP"), max_length=255, blank=True, default="")
    port = models.PositiveIntegerField(_("port"), default=587)
    chiffrement = models.CharField(
        _("chiffrement"), max_length=10, choices=Chiffrement.choices, default=Chiffrement.STARTTLS
    )
    identifiant = models.CharField(_("identifiant"), max_length=254, blank=True, default="")
    mot_de_passe_chiffre = models.TextField(_("mot de passe chiffré"), blank=True, default="")
    expediteur = models.CharField(_("expéditeur"), max_length=254, blank=True, default="")
    modifie_le = models.DateTimeField(_("modifié le"), auto_now=True)

    class Meta:
        db_table = "parametres_messagerie"
        verbose_name = _("messagerie de la plateforme")
        verbose_name_plural = _("messagerie de la plateforme")

    def save(self, *args, **kwargs):
        # Une seule ligne, toujours la même : pas de doublon possible.
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def est_complete(self) -> bool:
        """Le réglage saisi est utilisable : sans lui, le serveur retombe sur le `.env`."""
        return bool(self.hote and self.identifiant and self.mot_de_passe_chiffre)

    def __str__(self) -> str:
        return f"{self.identifiant}@{self.hote}:{self.port}" if self.hote else "messagerie non configurée"
