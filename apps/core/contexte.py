"""Le contexte d'entreprise — quelle entreprise est active, pour ce fil d'exécution.

Décision D9 (`04_Conception/plan_technique/architecture_globale_systeme/
decision_schema_unique_CCD_Digital.md`) : toutes les entreprises partagent les mêmes tables, et
chaque ligne porte son `entreprise_id`. Ce module dit **à qui appartient la requête en cours** ;
les gestionnaires de `ModeleEntreprise` s'en servent pour filtrer.

Trois états, et un seul ouvre la porte :

- **une entreprise est active** (`contexte_entreprise`) : on ne voit que ses lignes ;
- **la portée plateforme est déclarée** (`portee_plateforme`) : le code de l'éditeur traverse
  les entreprises — chaque usage est nommé et journalisé ;
- **rien** : toute lecture ou écriture d'une table d'entreprise **lève `HorsContexteEntreprise`**.
  C'est la règle R-4 : une panne ferme la porte, jamais elle ne rend tout.

`contextvars` plutôt qu'une variable de fil : la valeur suit le fil d'exécution (une requête WSGI,
une tâche Celery) et se restaure d'elle-même à la sortie de chaque bloc `with`.
"""

from __future__ import annotations

import functools
import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

__all__ = [
    "HorsContexteEntreprise",
    "avec_entreprise",
    "contexte_entreprise",
    "en_portee_plateforme",
    "entreprise_courante_id",
    "exiger_entreprise",
    "portee_plateforme",
    "reinitialiser_contexte",
]

_entreprise: ContextVar[uuid.UUID | None] = ContextVar("ccd_entreprise", default=None)
_portee: ContextVar[str | None] = ContextVar("ccd_portee_plateforme", default=None)


class HorsContexteEntreprise(RuntimeError):  # noqa: N818 — nommage français du dépôt
    """Une table d'entreprise a été lue ou écrite sans entreprise active ni portée plateforme.

    C'est une erreur de programmation, pas une erreur de l'utilisateur : elle ne doit jamais être
    rattrapée pour « continuer quand même ».
    """


def _en_uuid(entreprise) -> uuid.UUID:
    """Accepte une entreprise, un UUID ou sa forme textuelle."""
    if entreprise is None:
        raise ValueError("Une entreprise est requise pour ouvrir un contexte d'entreprise.")
    valeur = getattr(entreprise, "pk", entreprise)
    return valeur if isinstance(valeur, uuid.UUID) else uuid.UUID(str(valeur))


def entreprise_courante_id() -> uuid.UUID | None:
    """L'entreprise active, ou `None`."""
    return _entreprise.get()


def en_portee_plateforme() -> bool:
    return _portee.get() is not None


def exiger_entreprise() -> uuid.UUID:
    """L'entreprise active ; lève `HorsContexteEntreprise` s'il n'y en a pas."""
    identifiant = _entreprise.get()
    if identifiant is None:
        raise HorsContexteEntreprise(
            "Aucune entreprise active : ouvrez un contexte_entreprise(...) ou, pour le code de "
            "la plateforme, une portee_plateforme(motif=...)."
        )
    return identifiant


@contextmanager
def contexte_entreprise(entreprise):
    """Active `entreprise` le temps du bloc, puis restaure le contexte précédent.

    Ouvrir une entreprise à l'intérieur d'une portée plateforme est permis : c'est le cas d'une
    tâche planifiée qui traite les entreprises une par une. Le contexte d'entreprise l'emporte
    alors sur la portée plateforme, le temps du bloc.
    """
    jeton_entreprise = _entreprise.set(_en_uuid(entreprise))
    jeton_portee = _portee.set(None)
    try:
        yield
    finally:
        _portee.reset(jeton_portee)
        _entreprise.reset(jeton_entreprise)


@contextmanager
def portee_plateforme(motif: str):
    """Déclare le code de l'éditeur qui traverse les entreprises.

    Le motif est obligatoire et journalisé : chaque usage doit pouvoir être retrouvé et relu en
    revue (`grep portee_plateforme`). Il ne s'ouvre pas pendant qu'une entreprise est active —
    élargir la portée d'une requête d'entreprise est précisément ce qu'on veut empêcher.
    """
    if not (motif or "").strip():
        raise ValueError("Une portée plateforme exige un motif.")
    if _entreprise.get() is not None:
        raise HorsContexteEntreprise(
            "Une portée plateforme ne s'ouvre pas pendant qu'une entreprise est active."
        )
    logger.info("Portée plateforme ouverte : %s", motif)
    jeton = _portee.set(motif.strip())
    try:
        yield
    finally:
        _portee.reset(jeton)


@contextmanager
def verification_plateforme(motif: str):
    """Une portée plateforme **le temps d'un test d'existence**, même sous une entreprise active.

    La seule exception à la règle de `portee_plateforme`, et elle est étroite : une règle qui vaut
    sur toute la plateforme (l'adresse e-mail est unique, R-8) se vérifie aussi pendant une
    requête d'entreprise — inviter un collaborateur, par exemple. Sous la RLS, l'entreprise active
    ne voit que ses comptes : le doublon d'une autre entreprise passerait le contrôle et
    échouerait sur la contrainte, en erreur 500.

    **Le bloc ne doit rendre qu'un booléen** (`.exists()`), jamais une ligne ni un identifiant.
    L'entreprise active est restaurée à la sortie.
    """
    if not (motif or "").strip():
        raise ValueError("Une vérification plateforme exige un motif.")
    jeton_entreprise = _entreprise.set(None)
    jeton_portee = _portee.set(motif.strip())
    try:
        yield
    finally:
        _portee.reset(jeton_portee)
        _entreprise.reset(jeton_entreprise)


def activer_entreprise(entreprise) -> None:
    """Active une entreprise **jusqu'à la fin de la requête** — réservé à l'authentification.

    Contrairement à `contexte_entreprise`, il n'y a pas de bloc à refermer : c'est le middleware
    `ContexteEntrepriseMiddleware` qui remet le contexte à zéro à la fin de chaque requête.
    """
    _entreprise.set(_en_uuid(entreprise))
    _portee.set(None)


def suspendre_contexte():
    """Vide le contexte et rend de quoi le restaurer (`restaurer_contexte`) — tâches Celery.

    Une tâche part toujours sans entreprise ni portée. Mais en mode *eager* (développement,
    cPanel), elle tourne **dans le fil de son appelant** : la vider sans restaurer laisserait la
    suite de la requête sans entreprise, et la prochaine lecture lèverait `HorsContexteEntreprise`.
    """
    return _entreprise.set(None), _portee.set(None)


def restaurer_contexte(jeton) -> None:
    """Rend le contexte que `suspendre_contexte` avait mis de côté."""
    jeton_entreprise, jeton_portee = jeton
    _portee.reset(jeton_portee)
    _entreprise.reset(jeton_entreprise)


def reinitialiser_contexte() -> None:
    """Remet le fil d'exécution sans entreprise ni portée (début et fin de requête, de tâche)."""
    _entreprise.set(None)
    _portee.set(None)


def avec_entreprise(fonction):
    """Décorateur de tâche : le premier argument est l'identifiant de l'entreprise.

        @shared_task
        @avec_entreprise
        def recalculer(entreprise_id, projet_id): ...

    Une tâche Celery n'hérite pas du contexte de la requête qui l'a lancée : elle reçoit
    l'entreprise en argument et l'ouvre elle-même. Sans cela, sa première requête lèverait
    `HorsContexteEntreprise` — là où, avec django-tenants, elle tournait sur `public` sans rien
    trouver et sans rien dire.
    """

    @functools.wraps(fonction)
    def enveloppe(entreprise_id, *args, **kwargs):
        with contexte_entreprise(entreprise_id):
            return fonction(entreprise_id, *args, **kwargs)

    return enveloppe
