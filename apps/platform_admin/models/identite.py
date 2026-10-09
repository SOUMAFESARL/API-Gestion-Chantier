"""Identité de la plateforme : le nom et le logo sous lesquels CCD Digital se présente.

Schéma : public. Une seule ligne existe (clé 1) : ce n'est pas une collection mais
un réglage, lu sans connexion par les pages publiques (connexion, tarifs).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

NOM_PAR_DEFAUT = "CCD Digital"


class IdentitePlateforme(models.Model):
    """Réglage unique : nom affiché et logo de la plateforme."""

    nom = models.CharField(_("nom"), max_length=120, default=NOM_PAR_DEFAUT)
    logo = models.ImageField(_("logo"), upload_to="plateforme/", null=True, blank=True)
    modifie_le = models.DateTimeField(_("modifié le"), auto_now=True)

    class Meta:
        db_table = "identite_plateforme"
        verbose_name = _("identité de la plateforme")
        verbose_name_plural = _("identité de la plateforme")

    def save(self, *args, **kwargs):
        # Une seule ligne, toujours la même : pas de doublon possible.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtenir(cls) -> "IdentitePlateforme":
        """La ligne unique, créée avec ses valeurs par défaut si elle n'existe pas encore."""
        identite, _cree = cls.objects.get_or_create(pk=1)
        return identite

    def __str__(self) -> str:
        return self.nom
