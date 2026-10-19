"""Service de synchronisation d'avancement physique depuis les rapports de chantier (F3).

Lorsqu'un rapport journalier est approuvé par le Chef de Projet (CP), les quantités
réalisées saisies (activités et production) sont reportées sur les activités concernées,
puis l'avancement physique des activités, des lots et du projet est recalculé et stocké.
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.chantier.models.rapport_journalier import RapportJournalier
from apps.core.enums import StatutRapport
from apps.projets.models import Activite, Lot, Projet
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_activite,
    calculer_avancement_physique_lot,
    calculer_avancement_physique_projet,
)
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

logger = logging.getLogger(__name__)

__all__ = ["synchroniser_rapport_approuve"]


@transaction.atomic
def synchroniser_rapport_approuve(rapport_id: uuid.UUID | str) -> bool:
    """Synchronise les quantités d'un rapport approuvé avec l'avancement physique.

    Étapes :
    1. Verrouille le rapport (select_for_update). Si non APPROUVE ou f3_sync_done, rend False.
    2. Lit le journal associé (si absent, marque f3_sync_done et rend True).
    3. Cumule les quantite_jour > 0 des lignes d'activités et de production.
    4. Met à jour quantite_realisee des activités trouvées et non supprimées.
    5. Recalcule et stocke l'avancement (activités touchées -> leurs lots -> projet).
    6. Marque f3_sync_done=True sur le rapport par update de queryset (évite post_save).
    7. Déclenche le recalcul réactif de l'indice de santé (RAPPORT_APPROBATION).

    Retourne True si la synchronisation a été effectuée ou marquée, False sinon.
    """
    rapport = RapportJournalier.objects.select_for_update().get(pk=rapport_id)
    if rapport.statut != StatutRapport.APPROUVE or rapport.f3_sync_done:
        return False

    try:
        journal = rapport.journal
    except ObjectDoesNotExist:
        journal = None

    if journal is None:
        RapportJournalier.objects.filter(pk=rapport.pk).update(f3_sync_done=True)
        return True

    saisie = journal.saisie or {}
    cumuls: dict[uuid.UUID, Decimal] = {}

    for section in ("activites", "production"):
        lignes = saisie.get(section) or []
        for ligne in lignes:
            if not isinstance(ligne, dict):
                continue
            q_brut = ligne.get("quantite_jour")
            if q_brut is None:
                continue
            try:
                q_dec = Decimal(str(q_brut))
            except (ValueError, TypeError, InvalidOperation):
                continue
            if q_dec <= Decimal("0"):
                continue
            act_id = ligne.get("activite_id")
            if not act_id:
                continue
            try:
                act_uuid = uuid.UUID(str(act_id)) if not isinstance(act_id, uuid.UUID) else act_id
            except (ValueError, TypeError, AttributeError):
                continue
            cumuls[act_uuid] = cumuls.get(act_uuid, Decimal("0")) + q_dec

    activites_touchees = list(
        Activite.objects.filter(pk__in=cumuls.keys(), supprime_le__isnull=True)
        .select_for_update()
        .order_by("pk")
    )

    lots_touches_ids: set[uuid.UUID] = set()
    for activite in activites_touchees:
        q_ajoute = cumuls.get(activite.pk, Decimal("0"))
        if q_ajoute > Decimal("0"):
            q_actuelle = activite.quantite_realisee or Decimal("0.000")
            activite.quantite_realisee = q_actuelle + q_ajoute
            av_act = calculer_avancement_physique_activite(activite)
            activite.avancement = Decimal(str(av_act)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            activite.save(update_fields=["quantite_realisee", "avancement"])
            if activite.lot_id:
                lots_touches_ids.add(activite.lot_id)

    if lots_touches_ids:
        lots = list(
            Lot.objects.filter(pk__in=lots_touches_ids, supprime_le__isnull=True)
            .select_for_update()
            .order_by("pk")
        )
        for lot in lots:
            av_lot = calculer_avancement_physique_lot(lot)
            lot.avancement = Decimal(str(av_lot)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            lot.save(update_fields=["avancement"])

    if rapport.projet_id:
        projet = Projet.objects.select_for_update().get(pk=rapport.projet_id)
        av_projet, _ = calculer_avancement_physique_projet(projet)
        projet.avancement_reel = Decimal(str(av_projet)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        projet.save(update_fields=["avancement_reel"])

    RapportJournalier.objects.filter(pk=rapport.pk).update(f3_sync_done=True)

    if rapport.projet_id:
        declencher_recalcul_sante(
            projet_id=rapport.projet_id,
            declencheur_type="RAPPORT_APPROBATION",
            declencheur_id=rapport.pk,
        )

    return True
