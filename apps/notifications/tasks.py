"""Tâches Celery du domaine des notifications."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.core.contexte import contexte_entreprise
from apps.core.emails import envoyer_email_notification

logger = logging.getLogger(__name__)

__all__ = [
    "envoyer_email_notification_async",
    "purger_anciennes_notifications_toutes_entreprises",
]


@shared_task(name="apps.notifications.tasks.envoyer_email_notification_async")
def envoyer_email_notification_async(
    email: str,
    sujet: str,
    message: str,
    *,
    lien_action: str | None = None,
    libelle_action: str = "Consulter dans l'application",
    prenom: str = "",
    details: dict[str, Any] | None = None,
    entreprise_id: str | None = None,
) -> bool:
    """Envoie un e-mail de notification de manière asynchrone via Celery.

    Exécuté dans le contexte de l'entreprise si `entreprise_id` est fourni.
    """
    try:
        if entreprise_id:
            with contexte_entreprise(entreprise_id):
                return envoyer_email_notification(
                    destinataire=email,
                    sujet=sujet,
                    message=message,
                    lien_action=lien_action,
                    libelle_action=libelle_action,
                    prenom=prenom,
                    details=details,
                )
        return envoyer_email_notification(
            destinataire=email,
            sujet=sujet,
            message=message,
            lien_action=lien_action,
            libelle_action=libelle_action,
            prenom=prenom,
            details=details,
        )
    except Exception:
        logger.exception("Échec lors de l'envoi asynchrone de l'e-mail à %s", email)
        return False


@shared_task(name="apps.notifications.tasks.purger_anciennes_notifications_toutes_entreprises")
def purger_anciennes_notifications_toutes_entreprises() -> dict[str, int]:
    """Purge physique automatique des notifications de plus de 90 jours (MLD §5.5, Socle §3.1)."""
    from apps.notifications.services.purge import purger_notifications_anciennes

    return purger_notifications_anciennes(jours=90)
