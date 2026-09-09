"""Tâches Celery du module. Elles appellent un service, jamais l'inverse."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def provisionner_entreprise(self, identifiant: str) -> None:
    """Crée l'espace d'une entreprise — contrat d'inscription §5, effet 5.

    **La tâche ne porte que l'identifiant de la demande.** Le mot de passe reste
    en base, haché, et n'entre jamais dans la charge utile — R-86 : un message
    Celery traverse Redis, s'y attarde, et s'affiche dans les outils de
    supervision.

    **Elle n'a pas besoin de `schema_context` pour démarrer** : elle travaille
    d'abord dans `public`, où vit la demande. C'est le service qui bascule vers
    le schéma du client une fois celui-ci créé — et c'est là que le piège de la
    règle 3 se referme, `migrate_schemas` repositionnant la connexion sur
    `public` juste avant.
    """
    from apps.tenants.services.inscription import provisionner

    try:
        provisionner(identifiant)
    except Exception as erreur:
        # La demande est déjà passée à `ECHEC` par la compensation du service :
        # l'écran d'attente saura quoi afficher même si les reprises échouent.
        logger.exception("Provisionnement en échec — demande %s", identifiant)
        raise self.retry(exc=erreur) from erreur
