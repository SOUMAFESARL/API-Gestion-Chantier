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


# --------------------------------------------------------------------------
# Cloisonnement par entreprise — décision D9, règle R-4
# --------------------------------------------------------------------------
class RequeteEntreprise(RequeteSansSupprimes):
    """QuerySet d'une table d'entreprise : ne voit que l'entreprise active, refuse sans elle.

    **Le filtre se décide à l'évaluation, pas à la création.** Django crée des querysets au
    chargement du code (`queryset=Projet.objects.all()` d'un champ de serializer, d'un filtre) :
    à ce moment, aucune entreprise n'est active, et refuser casserait le démarrage. Un queryset
    créé hors contexte reste donc « à cloisonner », et le cloisonnement s'applique juste avant
    d'interroger la base — avec l'entreprise active **à ce moment-là**, ou une erreur s'il n'y en
    a pas.

    Créé dans un contexte (le cas de toute vue), le queryset est filtré tout de suite : il reste
    alors correct même utilisé comme sous-requête (`filter(x__in=qs)`), cas que l'évaluation
    différée ne voit pas. Pour ce cas-là, la sécurité au niveau des lignes de PostgreSQL
    (couche 2, lot 4) reste le filet.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cloisonnement_a_appliquer = False

    def _clone(self):
        clone = super()._clone()
        clone._cloisonnement_a_appliquer = self._cloisonnement_a_appliquer
        return clone

    @classmethod
    def cloisonnee(cls, model, using=None):
        """Point d'entrée des gestionnaires : filtrée tout de suite si une entreprise est active."""
        from apps.core.contexte import en_portee_plateforme, entreprise_courante_id

        requete = cls(model, using=using)
        if en_portee_plateforme():
            return requete
        identifiant = entreprise_courante_id()
        if identifiant is not None:
            return requete.filter(entreprise_id=identifiant)
        requete._cloisonnement_a_appliquer = True
        return requete

    def _cloisonner(self) -> None:
        """Applique, sur place, le cloisonnement différé — ou refuse."""
        if not self._cloisonnement_a_appliquer:
            return
        from apps.core.contexte import en_portee_plateforme, exiger_entreprise

        if not en_portee_plateforme():
            self.query.add_q(models.Q(entreprise_id=exiger_entreprise()))
        self._cloisonnement_a_appliquer = False

    # Toutes les portes vers la base passent par l'une de ces méthodes.
    def _fetch_all(self):
        self._cloisonner()
        super()._fetch_all()

    def iterator(self, *args, **kwargs):
        self._cloisonner()
        return super().iterator(*args, **kwargs)

    def count(self):
        self._cloisonner()
        return super().count()

    def exists(self):
        self._cloisonner()
        return super().exists()

    def aggregate(self, *args, **kwargs):
        self._cloisonner()
        return super().aggregate(*args, **kwargs)

    def update(self, **kwargs):
        self._cloisonner()
        return super().update(**kwargs)

    def delete(self):
        self._cloisonner()
        return super().delete()

    def explain(self, *args, **kwargs):
        self._cloisonner()
        return super().explain(*args, **kwargs)


def _classe_requete(manager) -> type[RequeteEntreprise]:
    """Le QuerySet d'un gestionnaire cloisonné : le sien s'il dérive de `RequeteEntreprise`
    (gestionnaire construit par `from_queryset`), sinon `RequeteEntreprise`."""
    classe = getattr(manager, "_queryset_class", None)
    return classe if isinstance(classe, type) and issubclass(classe, RequeteEntreprise) else (
        RequeteEntreprise
    )


class ManagerEntrepriseActif(ManagerActif):
    """`objects` d'une table d'entreprise : entreprise active, lignes non supprimées."""

    def get_queryset(self):
        return _classe_requete(self).cloisonnee(self.model, using=self._db).filter(
            supprime_le__isnull=True
        )


class ManagerEntrepriseComplet(ManagerComplet):
    """`tous_objets` d'une table d'entreprise : entreprise active, supprimés compris.

    Cloisonné lui aussi : il sert à la numérotation des références et à la restauration, qui
    ne doivent jamais compter ni montrer les lignes d'une autre entreprise.
    """

    def get_queryset(self):
        return _classe_requete(self).cloisonnee(self.model, using=self._db)


# --------------------------------------------------------------------------
# La table des comptes — décision D9, règle R-8
# --------------------------------------------------------------------------
class RequeteComptes(RequeteEntreprise):
    """La table `utilisateur` : les comptes de l'entreprise active, ou le personnel de l'éditeur.

    Elle partage tout de `RequeteEntreprise`, sauf ce qu'elle fait **sans entreprise active** :
    elle ne refuse pas, elle rend le **personnel de CCD Digital** (`entreprise` nulle). C'est ce
    que rendait la table `utilisateur` du schéma `public` sous django-tenants, et ce qu'attend le
    code de l'administration de la plateforme, qui tourne sans entreprise.

    | Contexte | Comptes visibles |
    |---|---|
    | une entreprise active | ses collaborateurs |
    | aucun | le personnel de l'éditeur |
    | portée plateforme | tous |

    Retrouver un compte **avant** de connaître son entreprise (connexion, lien de
    réinitialisation) passe donc par une portée plateforme nommée, jamais par un filtre oublié.
    """

    def _cloisonner(self) -> None:
        if not self._cloisonnement_a_appliquer:
            return
        from apps.core.contexte import en_portee_plateforme, entreprise_courante_id

        if not en_portee_plateforme():
            identifiant = entreprise_courante_id()
            self.query.add_q(
                models.Q(entreprise_id=identifiant)
                if identifiant is not None
                else models.Q(entreprise__isnull=True)
            )
        self._cloisonnement_a_appliquer = False


class ManagerComptesComplet(ManagerComplet):
    """`tous_objets` de la table des comptes : cloisonné comme `objects`, supprimés compris."""

    def get_queryset(self):
        return RequeteComptes.cloisonnee(self.model, using=self._db)


class ManagerComptesActif(ManagerActif):
    """`objects` d'une table rattachée à un compte (jetons…) : cloisonnée comme `utilisateur`."""

    def get_queryset(self):
        return RequeteComptes.cloisonnee(self.model, using=self._db).filter(
            supprime_le__isnull=True
        )
