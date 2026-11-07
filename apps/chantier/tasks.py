"""Tâches Celery du module. Elles appellent un service, jamais l'inverse."""

import logging

from celery import shared_task
from apps.core.contexte import contexte_entreprise

logger = logging.getLogger(__name__)


def relancer_rapports_manquants_partout(slug: str | None = None) -> dict:
    """La relance de 17 h 30 dans chaque entreprise active, ou dans l'entreprise `slug` seule.

    Partagée par la tâche Celery Beat et par la commande
    `relancer_rapports_manquants` : sur cPanel, Passenger ne lance pas Celery
    Beat, c'est le cron de l'hébergeur qui appelle la commande.
    """
    from apps.chantier.services.relance import relancer_rapports_manquants
    from apps.core.enums import StatutEntreprise
    from apps.entreprises.models import Entreprise

    entreprises = Entreprise.objects.all().filter(
        statut__in=[StatutEntreprise.ACTIF, StatutEntreprise.ESSAI]
    )
    if slug:
        entreprises = entreprises.filter(slug=slug)
    bilan = {}
    for entreprise in entreprises:
        # Une tâche n'hérite pas du contexte de la requête : sans celui-ci, sa première requête
        # lèverait `HorsContexteEntreprise` (D9, R-4).
        try:
            with contexte_entreprise(entreprise):
                bilan[entreprise.slug] = relancer_rapports_manquants()
        except Exception:
            logger.exception("Relance automatique en échec pour %s", entreprise.slug)
            bilan[entreprise.slug] = {"erreur": True}
    logger.info("Relance automatique des rapports manquants : %s", bilan)
    return bilan


@shared_task
def relancer_rapports_manquants_toutes_entreprises() -> dict:
    """Celery Beat, 17 h 30 du lundi au vendredi (heure du chantier)."""
    return relancer_rapports_manquants_partout()
