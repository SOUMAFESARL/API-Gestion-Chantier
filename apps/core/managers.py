"""Managers — application de la suppression logique (RG-06).

Le manager **par défaut** ne voit jamais les lignes supprimées. C'est ce qui
rend la règle du Socle Commun §3.1 vraie par construction : un développeur
qui écrit `Projet.objects.all()` ne peut pas ressortir un projet supprimé,
même s'il ignore l'existence de la règle.

L'accès aux lignes supprimées est explicite et réservé à la restauration :
`Projet.tous_objets.filter(supprime_le__isnull=False)`.
"""

from django.db import models


class RequeteSansSupprimes(models.QuerySet):
    """QuerySet filtrant les lignes supprimées logiquement."""

    def supprimer_logiquement(self, utilisateur=None):
        """Suppression logique en masse. Ne supprime **jamais** physiquement."""
        from django.utils import timezone

        return self.update(supprime_le=timezone.now(), supprime_par=utilisateur)

    def restaurer(self):
        return self.update(supprime_le=None, supprime_par=None)


class ManagerActif(models.Manager):
    """Manager par défaut : exclut les lignes supprimées."""

    def get_queryset(self):
        return RequeteSansSupprimes(self.model, using=self._db).filter(supprime_le__isnull=True)


class ManagerComplet(models.Manager):
    """Manager explicite : voit tout, supprimés compris."""

    def get_queryset(self):
        return RequeteSansSupprimes(self.model, using=self._db)

    def supprimes(self):
        return self.get_queryset().filter(supprime_le__isnull=False)
