"""Tâches Celery pour l'application projets."""

import logging
from celery import shared_task
from django_tenants.utils import schema_context

from apps.core.emails import envoyer
from apps.core.enums import RoleGlobal

logger = logging.getLogger(__name__)

__all__ = [
    "evaluer_sante_projets_quotidien_tous_tenants",
    "evaluer_statuts_quotidiens_tous_tenants",
    "notifier_dg_derive_delai",
    "recalculer_sante_projet_task",
]


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
    return rapport_global


@shared_task
def recalculer_sante_projet_task(
    schema_name: str,
    projet_id: str,
    declencheur_type: str = "",
    declencheur_id: str | None = None,
) -> dict | None:
    """Tâche Celery réactive : recalcule l'indice de santé du projet.

    Conforme C8 :
    1. Efface la clé Redis 'en attente' au tout début de la tâche avant lecture DB.
    2. Exécute le calcul dans schema_context(schema_name).
    3. Verrouille le projet via select_for_update() dans une transaction atomique.
    4. Persiste l'avancement physique, l'avancement théorique, le score et le badge final.
    5. Enregistre un SanteProjetSnapshot d'audit.
    6. En cas de transition vers le ROUGE (ancien != ROUGE et nouveau == ROUGE), alerte par email post-commit.
    """
    from decimal import Decimal
    from django.core.cache import cache
    from django.db import transaction
    from apps.core.enums import BadgeSante
    from apps.projets.models import Projet, SanteProjetSnapshot
    from apps.projets.services.sante_calculs import calculer_indice_sante_projet
    from apps.projets.services.sante_declencheur import obtenir_cle_recalcul_en_attente

    # 1. Effacement immédiat de la clé Redis en début d'exécution (C8)
    cle = obtenir_cle_recalcul_en_attente(schema_name, projet_id)
    cache.delete(cle)

    def _executer():
        with transaction.atomic():
            projet = (
                Projet.objects.select_for_update()
                .filter(id=projet_id, supprime_le__isnull=True)
                .first()
            )
            if not projet:
                logger.warning(
                    "Recalcul santé ignoré : projet %s introuvable sur le schéma %s.",
                    projet_id,
                    schema_name,
                )
                return None

            ancien_badge = projet.badge_sante

            res = calculer_indice_sante_projet(projet)

            if res.etat == "NON_DEMARRE":
                projet.avancement_reel = Decimal("0.0")
                projet.indice_sante = None
                projet.badge_sante = None
                projet.save(update_fields=["avancement_reel", "indice_sante", "badge_sante", "modifie_le"])
                return {"projet_id": projet_id, "etat": "NON_DEMARRE", "score": None, "badge": None}

            if res.etat == "FIGE":
                return {
                    "projet_id": projet_id,
                    "etat": "FIGE",
                    "score": projet.indice_sante,
                    "badge": projet.badge_sante,
                }

            # État ACTIF : mise à jour du projet
            projet.avancement_reel = Decimal(str(res.avancement_physique))
            projet.avancement_theorique = Decimal(str(res.avancement_temporel))
            projet.indice_sante = res.score
            projet.badge_sante = res.badge_final
            projet.save(
                update_fields=[
                    "avancement_reel",
                    "avancement_theorique",
                    "indice_sante",
                    "badge_sante",
                    "modifie_le",
                ]
            )

            # Création du snapshot immuable
            snapshot = SanteProjetSnapshot.objects.create(
                projet=projet,
                score=res.score or 0,
                badge_brut=res.badge_brut or "",
                badge_final=res.badge_final or "",
                plancher_applique=res.plancher_applique,
                p_delais=Decimal(str(res.p_delais)),
                p_retard=Decimal(str(res.p_retard)),
                p_malus=Decimal(str(res.p_malus)),
                p_blocages=Decimal(str(res.p_blocages)),
                p_reporting=Decimal(str(res.p_reporting)),
                avancement_physique=Decimal(str(res.avancement_physique)),
                avancement_temporel=Decimal(str(res.avancement_temporel)),
                delta=Decimal(str(res.retard_pts)),
                mode_ponderation=res.mode_ponderation,
                nb_reports=res.nb_reports,
                blocages_ouverts_par_severite=res.blocages_ouverts_par_severite,
                taux_reporting=Decimal(str(res.taux_reporting)),
                jours_attendus=res.jours_attendus,
                jours_couverts=res.jours_couverts,
                declencheur_type=declencheur_type or "",
                declencheur_id=str(declencheur_id) if declencheur_id else "",
            )

            # Détection de transition vers le ROUGE (C8, C9)
            alerte_rouge = False
            if ancien_badge != BadgeSante.ROUGE and res.badge_final == BadgeSante.ROUGE:
                from apps.projets.services.sante_email import envoyer_alerte_sante_rouge

                alerte_rouge = True
                transaction.on_commit(
                    lambda: envoyer_alerte_sante_rouge(schema_name, str(projet.id), str(snapshot.id))
                )

            return {
                "projet_id": projet_id,
                "etat": "ACTIF",
                "score": res.score,
                "badge": res.badge_final,
                "alerte_rouge": alerte_rouge,
                "snapshot_id": str(snapshot.id),
            }

    if schema_name:
        with schema_context(schema_name):
            return _executer()
    return _executer()


@shared_task
def evaluer_sante_projets_quotidien_tous_tenants() -> dict:
    """Tâche Celery Beat quotidienne (00h15) : évalue et actualise l'indice de santé sur tous les tenants actifs."""
    from apps.core.enums import StatutEntreprise, StatutProjet
    from apps.projets.models import Projet
    from apps.tenants.models import Entreprise

    entreprises = Entreprise.objects.exclude(schema_name="public").filter(
        statut__in=[StatutEntreprise.ACTIF, StatutEntreprise.ESSAI]
    )
    rapport_global = {}

    statuts_actifs = {
        StatutProjet.EN_COURS,
        StatutProjet.EN_RETARD,
        StatutProjet.CRITIQUE,
        StatutProjet.BLOQUE,
    }

    for ent in entreprises:
        if not ent.schema_name:
            continue
        try:
            with schema_context(ent.schema_name):
                projets_actifs = list(
                    Projet.objects.filter(
                        supprime_le__isnull=True,
                        statut__in=statuts_actifs,
                    ).values_list("id", flat=True)
                )
                recalcules = 0
                for pid in projets_actifs:
                    recalculer_sante_projet_task(
                        schema_name=ent.schema_name,
                        projet_id=str(pid),
                        declencheur_type="JOB_QUOTIDIEN_00H15",
                    )
                    recalcules += 1

                rapport_global[ent.schema_name] = {
                    "projets_actifs_recalcules": recalcules,
                }
                logger.info(
                    "Évaluation quotidienne santé réussie pour tenant '%s' : %d projets recalculés.",
                    ent.schema_name,
                    recalcules,
                )
        except Exception as e:
            logger.error(
                "Erreur lors de l'évaluation quotidienne santé pour tenant '%s' : %s",
                ent.schema_name,
                e,
                exc_info=True,
            )
            rapport_global[ent.schema_name] = {"erreur": str(e)}

    return rapport_global
