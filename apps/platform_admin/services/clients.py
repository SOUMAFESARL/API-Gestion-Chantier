"""Services métier pour les actions d'administration sur les entreprises clientes."""

import logging
import uuid

from django.utils import timezone
from django_tenants.utils import get_public_schema_name
from rest_framework.exceptions import NotFound, ValidationError

from apps.billing.models import Abonnement, Plan
from apps.core.enums import StatutEntreprise
from apps.core.exceptions import ErreurConflit
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.selectors.clients import (
    MAP_PLAN_FRONTEND_VERS_BACKEND,
    formater_client_plateforme,
)
from apps.tenants.models import Entreprise

logger = logging.getLogger(__name__)


def suspendre_client_plateforme(
    entreprise_id: uuid.UUID | str,
    motif: str,
    admin_user=None,
    adresse_ip: str | None = None,
    appareil: str = "",
    **kwargs,
) -> dict:
    """Suspend l'accès d'une entreprise cliente et enregistre l'action au journal."""
    public_schema = get_public_schema_name()
    ent = Entreprise.objects.filter(pk=entreprise_id).exclude(schema_name=public_schema).first()
    if not ent:
        raise NotFound("Entreprise cliente introuvable.")

    if ent.statut == StatutEntreprise.SUSPENDU:
        raise ErreurConflit(detail="Cette entreprise cliente est déjà suspendue.")

    ent.statut = StatutEntreprise.SUSPENDU
    ent.save(update_fields=["statut"])

    # Mettre également les abonnements actifs ou en essai en statut SUSPENDU
    for abt in ent.abonnements.filter(
        statut__in=[Abonnement.Statut.ACTIF, Abonnement.Statut.ESSAI]
    ):
        abt.statut = Abonnement.Statut.SUSPENDU
        abt.renouvellement_auto = False
        abt.save(update_fields=["statut", "renouvellement_auto", "modifie_le"])

    JournalPlateforme.objects.create(
        utilisateur_id=admin_user.id if admin_user else None,
        entreprise_id=ent.id,
        action="SUSPENSION_CLIENT",
        detail={"motif": motif},
        adresse_ip=adresse_ip,
        appareil=appareil,
    )

    logger.info(
        "Entreprise %s (%s) suspendue par %s. Motif : %s",
        ent.schema_name,
        ent.id,
        admin_user,
        motif,
    )
    return formater_client_plateforme(ent)


def reactiver_client_plateforme(
    entreprise_id: uuid.UUID | str,
    admin_user=None,
    adresse_ip: str | None = None,
    appareil: str = "",
    **kwargs,
) -> dict:
    """Réactive une entreprise cliente suspendue et rétablit son abonnement."""
    public_schema = get_public_schema_name()
    ent = Entreprise.objects.filter(pk=entreprise_id).exclude(schema_name=public_schema).first()
    if not ent:
        raise NotFound("Entreprise cliente introuvable.")

    if ent.statut != StatutEntreprise.SUSPENDU:
        raise ErreurConflit(detail="Seule une entreprise suspendue peut être réactivée.")

    ent.statut = StatutEntreprise.ACTIF
    ent.save(update_fields=["statut"])

    # Rétablir les abonnements suspendus
    aujourdhui = timezone.localdate()
    for abt in ent.abonnements.filter(statut=Abonnement.Statut.SUSPENDU):
        if abt.fin_essai and abt.fin_essai >= aujourdhui:
            abt.statut = Abonnement.Statut.ESSAI
        else:
            abt.statut = Abonnement.Statut.ACTIF
        abt.renouvellement_auto = True
        abt.save(update_fields=["statut", "renouvellement_auto", "modifie_le"])

    JournalPlateforme.objects.create(
        utilisateur_id=admin_user.id if admin_user else None,
        entreprise_id=ent.id,
        action="REACTIVATION_CLIENT",
        detail={},
        adresse_ip=adresse_ip,
        appareil=appareil,
    )

    logger.info("Entreprise %s (%s) réactivée par %s", ent.schema_name, ent.id, admin_user)
    return formater_client_plateforme(ent)


def changer_plan_client_plateforme(
    entreprise_id: uuid.UUID | str,
    code_plan: str,
    admin_user=None,
    adresse_ip: str | None = None,
    appareil: str = "",
    **kwargs,
) -> dict:
    """Modifie le forfait d'abonnement d'une entreprise cliente."""
    public_schema = get_public_schema_name()
    ent = Entreprise.objects.filter(pk=entreprise_id).exclude(schema_name=public_schema).first()
    if not ent:
        raise NotFound("Entreprise cliente introuvable.")

    code_backend = MAP_PLAN_FRONTEND_VERS_BACKEND.get(code_plan, code_plan)
    nouveau_plan = (
        Plan.objects.filter(code=code_backend).first()
        or Plan.objects.filter(code=code_plan).first()
    )

    if not nouveau_plan:
        raise ValidationError({"plan_code": f"Le forfait '{code_plan}' est introuvable."})

    abonnement = (
        ent.abonnements.filter(
            statut__in=[Abonnement.Statut.ACTIF, Abonnement.Statut.ESSAI]
        ).first()
        or ent.abonnements.first()
    )

    ancien_code = abonnement.plan.code if abonnement and abonnement.plan else None

    if abonnement:
        abonnement.plan = nouveau_plan
        abonnement.save(update_fields=["plan", "modifie_le"])
    else:
        aujourdhui = timezone.localdate()
        Abonnement.objects.create(
            entreprise=ent,
            plan=nouveau_plan,
            date_debut=aujourdhui,
            date_fin=aujourdhui + timezone.timedelta(days=30),
            statut=Abonnement.Statut.ACTIF,
            renouvellement_auto=True,
        )

    JournalPlateforme.objects.create(
        utilisateur_id=admin_user.id if admin_user else None,
        entreprise_id=ent.id,
        action="CHANGEMENT_PLAN",
        detail={
            "ancien_plan": ancien_code,
            "nouveau_plan": nouveau_plan.code,
        },
        adresse_ip=adresse_ip,
        appareil=appareil,
    )

    logger.info(
        "Forfait de l'entreprise %s modifié de %s vers %s par %s",
        ent.schema_name,
        ancien_code,
        nouveau_plan.code,
        admin_user,
    )
    return formater_client_plateforme(ent)
