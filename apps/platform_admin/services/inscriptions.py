"""Decision administrative atomique avant le provisionnement du tenant."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import DemandeInscription


class DecisionImpossible(APIException):
    status_code = 409
    default_detail = "Cette demande n'est pas en attente de validation."


@transaction.atomic
def decider_inscription(identifiant, utilisateur, *, approuver, motif="", adresse_ip=None):
    demande = get_object_or_404(DemandeInscription.objects.select_for_update(), pk=identifiant)
    if demande.decision_le:
        if (approuver and demande.statut in ("PROVISIONNEMENT", "ACTIVEE")) or (
            not approuver and demande.statut == "REFUSEE"
        ):
            return demande
        raise DecisionImpossible()
    if demande.statut != "A_VALIDER" or not demande.utilise_le:
        raise DecisionImpossible()
    demande.statut = "PROVISIONNEMENT" if approuver else "REFUSEE"
    demande.decision_par = utilisateur.pk
    demande.decision_le = timezone.now()
    demande.motif_refus = "" if approuver else motif
    if not approuver:
        demande.mot_de_passe_transitoire = ""
    demande.save(
        update_fields=[
            "statut",
            "decision_par",
            "decision_le",
            "motif_refus",
            "mot_de_passe_transitoire",
            "modifie_le",
        ]
    )
    JournalPlateforme.objects.create(
        utilisateur_id=utilisateur.pk,
        action="INSCRIPTION_APPROUVEE" if approuver else "INSCRIPTION_REFUSEE",
        adresse_ip=adresse_ip,
        detail={"demande_id": str(demande.pk), "motif": demande.motif_refus},
    )
    if approuver:
        from apps.tenants.tasks import provisionner_entreprise

        transaction.on_commit(lambda: provisionner_entreprise.delay(str(demande.pk)))
    return demande
