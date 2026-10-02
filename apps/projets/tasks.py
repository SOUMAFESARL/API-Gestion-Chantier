"""Tâches Celery pour l'application projets."""

import logging
from celery import shared_task
from django_tenants.utils import schema_context

from apps.core.emails import envoyer
from apps.core.enums import RoleGlobal

logger = logging.getLogger(__name__)

__all__ = ["evaluer_statuts_quotidiens_tous_tenants", "notifier_dg_derive_delai"]


@shared_task
def notifier_dg_derive_delai(
    schema_name: str | None,
    type_objet: str,
    objet_id: str,
    jours_derive: int,
    motif_libelle: str = "",
    justification: str = "",
) -> int:
    """Alerte par email la Direction Générale en cas de report supérieur à 30 jours (US-033)."""
    from apps.accounts.models import Utilisateur
    from apps.projets.models import Activite, Lot, Projet

    def _traiter() -> int:
        instance = None
        projet = None
        lot = None
        activite = None

        if type_objet == "PROJET":
            instance = projet = Projet.objects.filter(id=objet_id).first()
        elif type_objet == "LOT":
            lot = instance = Lot.objects.select_related("projet").filter(id=objet_id).first()
            if lot:
                projet = lot.projet
        elif type_objet == "ACTIVITE":
            activite = instance = (
                Activite.objects.select_related("lot", "lot__projet").filter(id=objet_id).first()
            )
            if activite:
                lot = activite.lot
                projet = lot.projet

        if not instance or not projet:
            logger.warning(
                "Impossible d'envoyer l'alerte dérive : objet %s (%s) introuvable.",
                objet_id,
                type_objet,
            )
            return 0

        # Récupération des destinataires DG et Admin
        dgs = Utilisateur.objects.filter(
            supprime_le__isnull=True,
            is_active=True,
        ).filter(
            models_q_dg()
        )
        destinataires = [u.email for u in dgs if u.email]
        if not destinataires:
            logger.info("Aucun destinataire DG trouvé pour l'alerte dérive (schéma: %s).", schema_name)
            return 0

        type_libelles = {
            "PROJET": "Projet",
            "LOT": "Lot de travaux",
            "ACTIVITE": "Activité",
        }

        contexte = {
            "type_objet_libelle": type_libelles.get(type_objet, type_objet),
            "objet_nom": str(instance),
            "projet_nom": projet.nom,
            "lot_nom": lot.libelle if lot else None,
            "activite_nom": activite.libelle if activite else None,
            "date_fin_baseline": getattr(instance, "date_fin_baseline", None),
            "nouvelle_date_fin": getattr(instance, "date_fin_prevue", None),
            "jours_derive": jours_derive,
            "motif_libelle": motif_libelle,
            "justification": justification,
        }

        sujet = f"🚨 Alerte Dérive Délais (+{jours_derive} j) — {projet.nom}"
        succes = envoyer(
            gabarit="alerte_derive_delai",
            sujet=sujet,
            destinataires=destinataires,
            contexte=contexte,
        )
        return len(destinataires) if succes else 0

    def models_q_dg():
        from django.db.models import Q
        return Q(role_global=RoleGlobal.DIRECTEUR_GENERAL) | Q(role_global=RoleGlobal.ADMIN)

    if schema_name:
        with schema_context(schema_name):
            return _traiter()
    return _traiter()


@shared_task
def evaluer_statuts_quotidiens_tous_tenants() -> dict:
    """Tâche nocturne Celery Beat : évalue les statuts calendaires sur chaque schéma tenant actif."""
    from apps.core.enums import StatutEntreprise
    from apps.projets.services.machine_etats import executer_evaluation_quotidienne_schema
    from apps.tenants.models import Entreprise

    entreprises = Entreprise.objects.exclude(schema_name="public").filter(
        statut__in=[StatutEntreprise.ACTIF, StatutEntreprise.ESSAI]
    )
    rapport_global = {}

    for ent in entreprises:
        if not ent.schema_name:
            continue
        try:
            with schema_context(ent.schema_name):
                rapport = executer_evaluation_quotidienne_schema()
                rapport_global[ent.schema_name] = rapport
                logger.info(
                    "Évaluation quotidienne réussie pour tenant '%s' : %s",
                    ent.schema_name,
                    rapport,
                )
        except Exception as e:
            logger.error(
                "Erreur lors de l'évaluation quotidienne pour tenant '%s' : %s",
                ent.schema_name,
                e,
                exc_info=True,
            )
            rapport_global[ent.schema_name] = {"erreur": str(e)}

    return rapport_global
