"""Réactions aux événements du module. Branchés dans AppConfig.ready()."""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.chantier.models.rapport_journalier import RapportJournalier
from apps.core.enums import StatutRapport

logger = logging.getLogger(__name__)


def _synchroniser(rapport_id):
    from apps.projets.services.avancement import synchroniser_rapport_approuve

    with transaction.atomic():
        synchroniser_rapport_approuve(rapport_id)


@receiver(post_save, sender=RapportJournalier)
def synchroniser_avancement_apres_approbation(sender, instance, **kwargs):
    """Déclenche la synchronisation F3 lors de l'approbation d'un rapport journalier."""
    if instance.statut != StatutRapport.APPROUVE or instance.f3_sync_done:
        return
    transaction.on_commit(lambda: _synchroniser(instance.pk))
