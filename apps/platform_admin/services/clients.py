"""Services métier pour les actions d'administration sur les entreprises clientes."""

from datetime import date
import logging
import uuid

from django.db import transaction
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
from apps.platform_admin.services.notifications import (
    SUJET_MODIFICATION_PLATEFORME,
    journaliser_plateforme,
    journaliser_tenant,
    notifier_dg_action_plateforme,
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


def modifier_echeance_client_plateforme(
    entreprise_id: uuid.UUID | str,
    date_fin: date,
    motif: str,
    admin_user=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> dict:
    """Modifie la date d'échéance de l'abonnement en cours d'une entreprise cliente."""
    public_schema = get_public_schema_name()
    ent = Entreprise.objects.filter(pk=entreprise_id).exclude(schema_name=public_schema).first()
    if not ent:
        raise NotFound("Entreprise cliente introuvable.")

    abonnement = (
        ent.abonnements.filter(
            statut__in=[Abonnement.Statut.ACTIF, Abonnement.Statut.ESSAI]
        ).first()
        or ent.abonnements.first()
    )
    if not abonnement:
        raise ErreurConflit(detail="Cette entreprise n'a aucun abonnement à prolonger.")
    if abonnement.statut == Abonnement.Statut.RESILIE:
        raise ErreurConflit(
            detail="Un abonnement résilié ne se prolonge pas : il faut en souscrire un nouveau."
        )

    if date_fin < timezone.localdate():
        raise ValidationError(
            {"date_fin": "La date de fin ne peut pas être antérieure à aujourd'hui."}
        )

    if date_fin <= abonnement.date_debut:
        raise ValidationError(
            {"date_fin": "La date de fin doit être postérieure à la date de début de l'abonnement."}
        )

    ancienne_date_fin = abonnement.date_fin
    ancienne_fin_essai = abonnement.fin_essai
    nouvelle_fin_essai = (
        date_fin if abonnement.statut == Abonnement.Statut.ESSAI else ancienne_fin_essai
    )

    if date_fin == ancienne_date_fin and nouvelle_fin_essai == ancienne_fin_essai:
        return formater_client_plateforme(ent)

    with transaction.atomic():
        abonnement.date_fin = date_fin
        champs_maj = ["date_fin", "modifie_le"]
        if abonnement.statut == Abonnement.Statut.ESSAI:
            abonnement.fin_essai = date_fin
            champs_maj.append("fin_essai")
        abonnement.save(update_fields=champs_maj)

        detail_journal = {
            "ancienne_date_fin": ancienne_date_fin.isoformat() if ancienne_date_fin else None,
            "nouvelle_date_fin": date_fin.isoformat(),
            "ancienne_fin_essai": (
                ancienne_fin_essai.isoformat() if ancienne_fin_essai else None
            ),
            "nouvelle_fin_essai": (
                nouvelle_fin_essai.isoformat() if nouvelle_fin_essai else None
            ),
            "statut_abonnement": abonnement.statut,
            "motif": motif,
        }
        journaliser_plateforme(
            action="MODIFICATION_ECHEANCE",
            acteur=admin_user,
            entreprise=ent,
            detail=detail_journal,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        valeur_apres = {
            "date_fin": date_fin.isoformat(),
            "fin_essai": nouvelle_fin_essai.isoformat() if nouvelle_fin_essai else None,
        }
        journaliser_tenant(
            entreprise=ent,
            action="MODIFICATION",
            type_entite="Abonnement",
            entite_id=abonnement.id,
            valeur_apres=valeur_apres,
            acteur=admin_user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        date_formatee = date_fin.strftime("%d/%m/%Y")
        message_dg = (
            "Bonjour,\n\n"
            "La date de fin de votre abonnement a été modifiée par l'administration de la plateforme.\n"
            f"Nouvelle date de fin : {date_formatee}"
        )
        admin_email = getattr(admin_user, "email", "")
        notifier_dg_action_plateforme(
            entreprise=ent,
            sujet=SUJET_MODIFICATION_PLATEFORME,
            message=message_dg,
            super_admin_email=admin_email,
        )

    logger.info(
        "Échéance de l'entreprise %s modifiée vers %s par %s",
        ent.schema_name,
        date_fin,
        admin_user,
    )
    return formater_client_plateforme(ent)
