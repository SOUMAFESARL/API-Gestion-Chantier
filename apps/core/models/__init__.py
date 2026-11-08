"""Modèles abstraits — socle de toutes les entités du produit.

`ModeleBase` est le point d'application de trois règles du Socle Commun.
C'est pour cela qu'il est unique et obligatoire :

  §3.1  la suppression physique n'existe pas   → `supprime_le` / `supprime_par`
  §2.4  toute action est tracée                → `cree_par`, `modifie_le`
  §1.2  jamais d'heure locale en base          → TIMESTAMPTZ UTC

Décision D3 : clé primaire UUID, **générée côté client**. Ce n'est pas un
raffinement : l'application mobile crée des rapports hors connexion et doit
donc produire l'identifiant avant tout contact avec le serveur.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.managers import (
    ManagerActif,
    ManagerComplet,
    ManagerEntrepriseActif,
    ManagerEntrepriseComplet,
)

__all__ = ["ModeleBase", "ModeleEntreprise", "ModeleHorodate"]


class ModeleHorodate(models.Model):
    """Horodatage seul — pour les tables en insertion pure (audit, accès)."""

    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True, db_index=True)

    class Meta:
        abstract = True


class ModeleBase(models.Model):
    """Modèle de base de toute entité métier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True)
    modifie_le = models.DateTimeField(_("modifié le"), auto_now=True)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("créé par"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("Nul lorsque l'écriture vient du système."),
    )

    supprime_le = models.DateTimeField(
        _("supprimé le"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Non nul = ligne supprimée logiquement. Jamais de suppression physique."),
    )
    supprime_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("supprimé par"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = ManagerActif()
    tous_objets = ManagerComplet()

    class Meta:
        abstract = True

    # -- suppression logique ------------------------------------------------

    @property
    def est_supprime(self) -> bool:
        return self.supprime_le is not None

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        """Redirige la suppression vers une suppression **logique**.

        `objet.delete()` est le réflexe de tout développeur Django. Le
        détourner ici est la seule façon de garantir la règle du Socle
        Commun §3.1 sans compter sur la vigilance de chacun.
        """
        self.supprime_le = timezone.now()
        self.supprime_par = utilisateur
        self.save(update_fields=["supprime_le", "supprime_par", "modifie_le"])

    def supprimer_definitivement(self, using=None, keep_parents=False):
        """Suppression physique réelle.

        N'existe que pour les tests et les scripts de maintenance.
        **Ne jamais appeler depuis du code applicatif.**
        """
        return super().delete(using=using, keep_parents=keep_parents)

    def restaurer(self, utilisateur=None):
        self.supprime_le = None
        self.supprime_par = None
        self.save(update_fields=["supprime_le", "supprime_par", "modifie_le"])


class ErreurIsolation(ValueError):  # noqa: N818 — nommage français du dépôt
    """Une ligne d'entreprise est écrite pour une autre entreprise que l'entreprise active."""


class ModeleEntreprise(ModeleBase):
    """Modèle de base de toute table d'entreprise — décision D9.

    - **`entreprise`** porte l'appartenance de la ligne (règle R-2). Elle se remplit d'elle-même
      depuis le contexte d'entreprise à la création, et ne peut pas désigner une autre entreprise
      que l'entreprise active.
    - **`objects` et `tous_objets`** sont cloisonnés (règle R-4) : ils ne voient que l'entreprise
      active, et refusent de travailler sans elle (`HorsContexteEntreprise`).

    *Lot 1 de la sortie du multi-schéma* : aucun modèle n'en hérite encore. Le lot 2 y fait
    passer les tables d'entreprise une par une.
    """

    entreprise = models.ForeignKey(
        "entreprises.Entreprise",
        on_delete=models.PROTECT,
        related_name="+",
        db_index=True,
        verbose_name=_("entreprise"),
        editable=False,
    )

    objects = ManagerEntrepriseActif()
    tous_objets = ManagerEntrepriseComplet()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self._poser_entreprise()
        super().save(*args, **kwargs)

    def _poser_entreprise(self) -> None:
        """Remplit `entreprise_id` depuis le contexte, ou refuse (R-2).

        Une seule règle, appelée par `save()` **et** par `bulk_create` (qui n'appelle jamais
        `save()` : sans cela, les lignes insérées en masse partaient sans entreprise).
        """
        from apps.core.contexte import (
            en_portee_plateforme,
            entreprise_courante_id,
            exiger_entreprise,
        )

        active = entreprise_courante_id()
        if self.entreprise_id is None:
            if en_portee_plateforme():
                raise ErreurIsolation(
                    "En portée plateforme, l'entreprise d'une nouvelle ligne se donne "
                    "explicitement : rien ne permet de la déduire."
                )
            self.entreprise_id = exiger_entreprise()
        elif active is not None and str(self.entreprise_id) != str(active):
            raise ErreurIsolation(
                f"Ligne de l'entreprise {self.entreprise_id} écrite pendant que "
                f"l'entreprise {active} est active."
            )

