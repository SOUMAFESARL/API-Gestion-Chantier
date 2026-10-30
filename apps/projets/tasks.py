"""Tâches Celery pour l'application projets."""

import logging

from celery import shared_task
from django_tenants.utils import schema_context

from apps.core.emails import envoyer
from apps.core.enums import RoleGlobal, StatutProjet

logger = logging.getLogger(__name__)

# Aucun import de apps.projets.services en tête de module : le paquet services importe
# ce module (reprogrammation → notifier_dg_derive_delai), et le worker Celery le charge
# en premier. Les services s'importent dans le corps des tâches.

__all__ = [
    "evaluer_f3_nuit_tous_tenants",
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
    from apps.projets.models import Element, Projet

    def _traiter() -> int:
        instance = None
        projet = None
        element = None

        if type_objet == "PROJET":
            instance = projet = Projet.objects.filter(id=objet_id).first()
        else:
            element = instance = (
                Element.objects.select_related("projet", "niveau").filter(id=objet_id).first()
            )
            if element:
                projet = element.projet

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

        contexte = {
            # Le libellé du niveau de la case (« Lot », « Ouvrage »…), jamais un type figé.
            "type_objet_libelle": element.niveau.libelle if element else "Projet",
            "objet_nom": str(instance),
            "projet_nom": projet.nom,
            "lot_nom": None,
            "activite_nom": element.libelle if element else None,
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
def evaluer_f3_nuit_tous_tenants() -> dict:
    """Tâche Celery Beat quotidienne de nuit à 00h01 (SFD F3 §4.6, §7).

    Pour chaque entreprise cliente sous son schema_context :
    1. Synchronise d'abord les rapports APPROUVE dont f3_sync_done est faux
       via synchroniser_rapport_approuve (rattrapage de coupure serveur).
    2. Recalcule l'indice de chaque projet suivi (appel direct de recalculer_sante_projet_task).
    3. Évalue ensuite le statut de chaque projet via evaluer_statut_projet.
    """
    from apps.chantier.models import RapportJournalier
    from apps.core.enums import StatutEntreprise, StatutRapport
    from apps.projets.models import Projet
    from apps.projets.services.alertes_retard import detecter_alertes_retard
    from apps.projets.services.avancement import synchroniser_rapport_approuve
    from apps.projets.services.indice_sante import STATUTS_SANTE_FIGES
    from apps.projets.services.machine_etats import (
        STATUTS_PROJET_MANUELS_FIXES,
        evaluer_statut_projet,
        evaluer_statuts_arbre,
    )
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
                # 1. Rattrapage des rapports approuvés non synchronisés
                rapports_a_rattraper = list(
                    RapportJournalier.objects.filter(
                        supprime_le__isnull=True,
                        statut=StatutRapport.APPROUVE,
                        f3_sync_done=False,
                    ).values_list("id", flat=True)
                )
                nb_rattrapes = 0
                for rap_id in rapports_a_rattraper:
                    try:
                        if synchroniser_rapport_approuve(rap_id):
                            nb_rattrapes += 1
                    except Exception as err:
                        logger.error(
                            "Erreur lors du rattrapage du rapport %s (tenant %s) : %s",
                            rap_id,
                            ent.schema_name,
                            err,
                            exc_info=True,
                        )

                # Évaluation préalable des cases de chaque arbre (mise à jour calendaire)
                for projet_arbre in Projet.objects.filter(supprime_le__isnull=True).iterator():
                    try:
                        evaluer_statuts_arbre(projet_arbre)
                    except Exception as err:
                        logger.error(
                            "Erreur d'évaluation des cases du projet %s (tenant %s) : %s",
                            projet_arbre.id,
                            ent.schema_name,
                            err,
                            exc_info=True,
                        )

                # 2. Recalcul de l'indice de chaque projet suivi (appel direct synchrone)
                projets_suivis = list(
                    Projet.objects.filter(
                        supprime_le__isnull=True,
                    ).exclude(
                        statut__in=STATUTS_SANTE_FIGES,
                    ).values_list("id", flat=True)
                )
                nb_indices = 0
                for pid in projets_suivis:
                    try:
                        recalculer_sante_projet_task(
                            schema_name=ent.schema_name,
                            projet_id=str(pid),
                            declencheur_type="JOB_NUIT_F3_00H01",
                        )
                        nb_indices += 1
                    except Exception as err:
                        logger.error(
                            "Erreur lors du recalcul de santé du projet %s (tenant %s) : %s",
                            pid,
                            ent.schema_name,
                            err,
                            exc_info=True,
                        )

                # 3. Évaluation du statut des projets
                projets_a_evaluer = list(
                    Projet.objects.filter(
                        supprime_le__isnull=True,
                    ).exclude(
                        statut__in=STATUTS_PROJET_MANUELS_FIXES,
                    )
                )
                nb_projets_modifies = 0
                for proj in projets_a_evaluer:
                    try:
                        if evaluer_statut_projet(proj):
                            nb_projets_modifies += 1

                    except Exception as err:
                        logger.error(
                            "Erreur lors de l'évaluation du statut du projet %s (tenant %s) : %s",
                            proj.id,
                            ent.schema_name,
                            err,
                            exc_info=True,
                        )

                    try:
                        detecter_alertes_retard(proj)
                    except Exception as err:
                        logger.error(
                            "Erreur lors de la détection des alertes de retard du "
                            "projet %s (tenant %s) : %s",
                            proj.id,
                            ent.schema_name,
                            err,
                            exc_info=True,
                        )

                rapport_global[ent.schema_name] = {
                    "rapports_rattrapes": nb_rattrapes,
                    "projets_indices_recalcules": nb_indices,
                    "projets_modifies": nb_projets_modifies,
                }
                logger.info(
                    "Évaluation F3 nuit réussie pour tenant '%s' : %s",
                    ent.schema_name,
                    rapport_global[ent.schema_name],
                )
        except Exception as e:
            logger.error(
                "Erreur lors de l'évaluation F3 nuit pour tenant '%s' : %s",
                ent.schema_name,
                e,
                exc_info=True,
            )
            rapport_global[ent.schema_name] = {"erreur": str(e)}

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
    6. En cas de transition vers le ROUGE (ancien != ROUGE et nouveau == ROUGE),
       alerte par email post-commit.
    """
    from decimal import Decimal

    from django.core.cache import cache
    from django.db import transaction
    from django.utils import timezone

    from apps.core.enums import BadgeSante
    from apps.projets.models import Projet, SanteProjetSnapshot
    from apps.projets.services.indice_sante import STATUTS_SANTE_FIGES, evaluer_indice_sante
    from apps.projets.services.sante_calculs import calculer_avancement_physique_projet
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

            if projet.statut == StatutProjet.EN_ATTENTE:
                projet.avancement_reel = Decimal("0")
                projet.indice_sante = None
                projet.badge_sante = None
                projet.save(
                    update_fields=[
                        "avancement_reel",
                        "indice_sante",
                        "badge_sante",
                        "modifie_le",
                    ]
                )
                return {
                    "projet_id": projet_id,
                    "etat": "NON_DEMARRE",
                    "score": None,
                    "badge": None,
                }

            if projet.statut in STATUTS_SANTE_FIGES:
                return {
                    "projet_id": projet_id,
                    "etat": "FIGE",
                    "score": projet.indice_sante,
                    "badge": projet.badge_sante,
                }

            ancien_badge = projet.badge_sante

            res = evaluer_indice_sante(projet)

            # Calcul des avancements pour persistance et snapshot
            av_physique, mode_pond = calculer_avancement_physique_projet(projet)
            av_temporel = float(round(av_physique + res.delta, 2))
            maintenant = timezone.now()

            # Mise à jour du projet (indice de la SFD, badge et horodatage de calcul)
            projet.avancement_reel = Decimal(str(av_physique))
            projet.avancement_theorique = Decimal(str(av_temporel))
            projet.indice_sante = res.indice
            projet.badge_sante = res.badge
            projet.indice_sante_calcule_le = maintenant
            projet.save(
                update_fields=[
                    "avancement_reel",
                    "avancement_theorique",
                    "indice_sante",
                    "badge_sante",
                    "indice_sante_calcule_le",
                    "modifie_le",
                ]
            )

            # Création du snapshot immuable d'historique avec scores SFD
            scores_snapshot = {
                "delais": res.scores.get("delais", 0),
                "rapports": res.scores.get("rapports", 0),
                "blocages": res.scores.get("blocages", 0),
                "incidents": res.scores.get("incidents", 0),
                "taux_rapports": res.taux_rapports,
            }
            snapshot = SanteProjetSnapshot.objects.create(
                projet=projet,
                score=res.indice,
                badge_brut=res.badge,
                badge_final=res.badge,
                plancher_applique=False,
                scores=scores_snapshot,
                p_delais=Decimal("0.0"),
                p_retard=Decimal("0.0"),
                p_malus=Decimal("0.0"),
                p_blocages=Decimal("0.0"),
                p_reporting=Decimal("0.0"),
                avancement_physique=Decimal(str(av_physique)),
                avancement_temporel=Decimal(str(av_temporel)),
                delta=Decimal(str(res.delta)),
                mode_ponderation=mode_pond,
                nb_reports=0,
                blocages_ouverts_par_severite={},
                taux_reporting=Decimal(str(round(res.taux_rapports / 100, 4))),
                jours_attendus=0,
                jours_couverts=0,
                declencheur_type=declencheur_type or "",
                declencheur_id=str(declencheur_id) if declencheur_id else "",
            )

            # Détection de transition vers le ROUGE (C8, C9)
            alerte_rouge = False
            if ancien_badge != BadgeSante.ROUGE and res.badge == BadgeSante.ROUGE:
                from apps.projets.services.sante_email import envoyer_alerte_sante_rouge

                alerte_rouge = True
                transaction.on_commit(
                    lambda: envoyer_alerte_sante_rouge(schema_name, str(projet.id), str(snapshot.id))
                )

            return {
                "projet_id": projet_id,
                "etat": "ACTIF",
                "score": res.indice,
                "badge": res.badge,
                "alerte_rouge": alerte_rouge,
                "snapshot_id": str(snapshot.id),
            }

    if schema_name:
        with schema_context(schema_name):
            return _executer()
    return _executer()


