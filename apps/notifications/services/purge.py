"""Service de purge automatique des notifications anciennes (MLD §5.5, Socle §3.1)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.contexte import contexte_entreprise
from apps.core.enums import StatutEntreprise
from apps.entreprises.models import Entreprise

logger = logging.getLogger(__name__)

__all__ = ["purger_notifications_anciennes"]


def purger_notifications_anciennes(jours: int = 90) -> dict[str, int]:
    """Purge physique des notifications antérieures au délai de rétention.

    Conformité MLD §5.5 et Socle §3.1 : seule suppression physique autorisée.
    """
    from apps.notifications.models import Notification

    limite = timezone.now() - timedelta(days=jours)
    entreprises = Entreprise.objects.filter(
        statut__in=[StatutEntreprise.ACTIF, StatutEntreprise.ESSAI]
    )

    bilan: dict[str, int] = {}
    for ent in entreprises:
        try:
            with contexte_entreprise(ent):
                nb_supprimees, _ = (
                    Notification.objects.filter(cree_le__lt=limite)
                    .delete()
                )
                bilan[str(ent.slug)] = nb_supprimees
        except Exception:
            logger.exception("Erreur lors de la purge des notifications pour %s", ent.slug)
            bilan[str(ent.slug)] = -1

    return bilan
