"""Service d'orchestration de la machine à états et d'évaluation quotidienne des chantiers.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets) & 2 (Suivi Technique des Travaux).

Invariants garantis :
1. Déclenchement strictement calendaire :
   - PLANIFIE (EN_ATTENTE) -> EN_COURS dès que date_du_jour >= date_debut_prevue.
   - EN_COURS -> EN_RETARD dès que date_du_jour > date_fin_prevue (si non réceptionné ni clôturé).
2. Rétablissement instantané en temps réel :
   - EN_RETARD -> EN_COURS dès qu'un décalage justifié (reprogrammation de date)
     repousse la date de fin à une date >= date_du_jour.
3. Verrou absolu de Réception :
   - Aucun projet ne peut passer à RECEPTIONNE (ou TERMINE) si 100 % de ses lots actifs
     ne sont pas au statut CLOTURE (ou avancement = 100 %).
4. Préservation des états manuels (puits stables) :
   - Les statuts SUSPENDU, BLOQUE, DESACTIVE, RESILIE, ARCHIVE, RECEPTIONNE et TERMINE
     ne sont jamais écrasés automatiquement par la tâche calendaire nocturne.
"""

from datetime import date
import logging
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from apps.core.enums import StatutActivite, StatutLot, StatutProjet
from apps.projets.models import Activite, Lot, Projet

logger = logging.getLogger(__name__)

__all__ = [
    "ProjetClosError",
    "STATUTS_ACHEVES",
    "STATUTS_FIN_DE_VIE",
    "STATUTS_PROJET_MANUELS_FIXES",
    "changer_statut_projet",
    "evaluer_statut_activite",
    "evaluer_statut_lot",
    "evaluer_statut_projet",
    "executer_evaluation_quotidienne_schema",
    "retablir_statut_apres_decalage_si_necessaire",
    "valider_transition_reception",
    "verifier_statut_projet_pour_ecriture",
]

from rest_framework import status as http_status
from rest_framework.exceptions import APIException


class ProjetClosError(APIException):
    status_code = http_status.HTTP_409_CONFLICT
    default_detail = "Le projet est clos (résilié, archivé ou désactivé)."
    default_code = "projet_clos"

    def __init__(self, detail=None, code=None):
        detail_msg = detail or self.default_detail
        code_val = code or self.default_code
        super().__init__(detail={"detail": detail_msg, "code": code_val})


STATUTS_FIN_DE_VIE = frozenset(
    {
        StatutProjet.RESILIE,
        StatutProjet.ARCHIVE,
        StatutProjet.DESACTIVE,
        "RESILIE",
        "ARCHIVE",
        "DESACTIVE",
    }
)

STATUTS_ACHEVES = frozenset(
    {
        StatutProjet.RECEPTIONNE,
        StatutProjet.TERMINE,
        "RECEPTIONNE",
        "TERMINE",
    }
)

STATUTS_PROJET_MANUELS_FIXES = frozenset(
    {
        StatutProjet.CRITIQUE,
        StatutProjet.SUSPENDU,
        StatutProjet.BLOQUE,
        StatutProjet.DESACTIVE,
        StatutProjet.RESILIE,
        StatutProjet.ARCHIVE,
        StatutProjet.RECEPTIONNE,
        StatutProjet.TERMINE,
    }
)


def verifier_statut_projet_pour_ecriture(projet, action="ECRITURE"):
    """Vérifie si l'état actuel du projet autorise l'écriture (Règle E-10).

    Lève ProjetClosError (HTTP 409 Conflict, code='projet_clos') si l'écriture est refusée.
    """
    if not projet:
        return
    statut = getattr(projet, "statut", None)
    if not statut:
        return

    # 1. Fin de vie : lecture seule absolue
    if statut in STATUTS_FIN_DE_VIE:
        raise ProjetClosError(
            detail="Le projet est clos (résilié, archivé ou désactivé). Aucune écriture n'est autorisée.",
            code="projet_clos",
        )

    # 2. Achèvement : interdiction des nouveaux rapports et des reprogrammations
    if statut in STATUTS_ACHEVES and action in ("NOUVEAU_RAPPORT", "REPROGRAMMATION"):
        raise ProjetClosError(
            detail="Le projet est achevé (réceptionné ou terminé). Cette opération n'est plus autorisée.",
            code="projet_clos",
        )


def evaluer_statut_activite(activite: Activite, date_reference: date | None = None) -> bool:
    """Évalue et met à jour le statut calendaire et d'avancement d'une activité.

    Retourne True si le statut a été modifié et sauvegardé, False sinon.
    """
    date_ref = date_reference or timezone.now().date()

    if activite.statut not in StatutActivite.values:
        return False

    if activite.avancement >= 100 or activite.statut == StatutActivite.CLOTURE:
        nouveau_statut = StatutActivite.CLOTURE
    elif activite.statut == StatutActivite.SUSPENDU:
        # Puits stable : suspension manuelle protégée
        return False
    elif activite.date_debut_prevue and date_ref < activite.date_debut_prevue:
        nouveau_statut = StatutActivite.PLANIFIE
    elif activite.date_fin_prevue and date_ref > activite.date_fin_prevue:
        nouveau_statut = StatutActivite.EN_RETARD
    else:
        nouveau_statut = StatutActivite.EN_COURS

    if activite.statut != nouveau_statut:
        ancien = activite.statut
        activite.statut = nouveau_statut
        activite.save(update_fields=["statut", "modifie_le"])
        logger.info(
            "Activité %s (%s) : statut mis à jour de %s -> %s",
            activite.id,
            activite.libelle,
            ancien,
            nouveau_statut,
        )
        if activite.lot and activite.lot.projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=activite.lot.projet_id,
                declencheur_type="ACTIVITE_STATUT_TRANSITION",
                declencheur_id=str(activite.id),
            )
        return True
    return False


def evaluer_statut_lot(lot: Lot, date_reference: date | None = None) -> bool:
    """Évalue et met à jour le statut calendaire et d'avancement d'un lot.

    Règle de clôture :
    - Si le lot possède des activités : clôturé si 100 % de ses activités actives sont CLOTURE.
    - Si le lot n'a pas d'activités : clôturé si son avancement >= 100 % ou déjà CLOTURE.

    Retourne True si le statut a été modifié et sauvegardé, False sinon.
    """
    date_ref = date_reference or timezone.now().date()

    if lot.statut not in StatutLot.values:
        return False

    if lot.statut == StatutLot.SUSPENDU:
        return False

    activites_actives = lot.activites.filter(supprime_le__isnull=True)
    if activites_actives.exists():
        toutes_cloturees = not activites_actives.exclude(statut=StatutActivite.CLOTURE).exists()
        if toutes_cloturees:
            nouveau_statut = StatutLot.CLOTURE
        elif lot.date_debut_prevue and date_ref < lot.date_debut_prevue:
            nouveau_statut = StatutLot.PLANIFIE
        elif lot.date_fin_prevue and date_ref > lot.date_fin_prevue:
            nouveau_statut = StatutLot.EN_RETARD
        else:
            nouveau_statut = StatutLot.EN_COURS
    else:
        if lot.avancement >= 100 or lot.statut == StatutLot.CLOTURE:
            nouveau_statut = StatutLot.CLOTURE
        elif lot.date_debut_prevue and date_ref < lot.date_debut_prevue:
            nouveau_statut = StatutLot.PLANIFIE
        elif lot.date_fin_prevue and date_ref > lot.date_fin_prevue:
            nouveau_statut = StatutLot.EN_RETARD
        else:
            nouveau_statut = StatutLot.EN_COURS

    if lot.statut != nouveau_statut:
        ancien = lot.statut
        lot.statut = nouveau_statut
        lot.save(update_fields=["statut", "modifie_le"])
        logger.info(
            "Lot %s (%s) : statut mis à jour de %s -> %s",
            lot.id,
            lot.libelle,
            ancien,
            nouveau_statut,
        )
        if lot.projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=lot.projet_id,
                declencheur_type="LOT_STATUT_TRANSITION",
                declencheur_id=str(lot.id),
            )
        return True
    return False


def evaluer_statut_projet(projet: Projet, date_reference: date | None = None) -> bool:
    """Évalue et met à jour le statut calendaire d'un projet.

    Règles :
    - Préserve les statuts manuels / terminaux (SUSPENDU, BLOQUE, RECEPTIONNE, etc.).
    - Strictement calendaire :
      * date_ref < date_debut_prevue -> EN_ATTENTE
      * date_ref > date_fin_prevue -> EN_RETARD
      * date_debut_prevue <= date_ref <= date_fin_prevue -> EN_COURS

    Retourne True si le statut a été modifié et sauvegardé, False sinon.
    """
    date_ref = date_reference or timezone.now().date()

    if projet.statut in STATUTS_PROJET_MANUELS_FIXES:
        return False

    if projet.date_debut_prevue and date_ref < projet.date_debut_prevue:
        nouveau_statut = StatutProjet.EN_ATTENTE
    elif projet.date_fin_prevue and date_ref > projet.date_fin_prevue:
        nouveau_statut = StatutProjet.EN_RETARD
    else:
        nouveau_statut = StatutProjet.EN_COURS

    if projet.statut != nouveau_statut:
        ancien = projet.statut
        projet.statut = nouveau_statut
        projet.save(update_fields=["statut", "modifie_le"])
        logger.info(
            "Projet %s (%s) : statut mis à jour de %s -> %s",
            projet.id,
            projet.reference,
            ancien,
            nouveau_statut,
        )
        from apps.projets.services.sante_declencheur import declencher_recalcul_sante

        declencher_recalcul_sante(
            projet_id=projet.id,
            declencheur_type="PROJET_STATUT_TRANSITION",
            declencheur_id=str(nouveau_statut),
        )
        return True
    return False


@transaction.atomic
def changer_statut_projet(
    projet: Projet,
    nouveau_statut: str,
    utilisateur=None,
) -> Projet:
    """Modifie le statut d'un projet avec gestion des effets de bord opérationnels (C2, F1).

    - Validation stricte de réception (100 % lots clôturés) si RECEPTIONNE.
    - Ouverture automatique d'un ArretChantier lors du passage à SUSPENDU.
    - Fermeture automatique de l'ArretChantier ouvert lors de la reprise (sortie de SUSPENDU).
    - Déclenchement réactif du recalcul de l'indice de santé.
    """
    ancien_statut = projet.statut

    if nouveau_statut == StatutProjet.RECEPTIONNE:
        valider_transition_reception(projet)

    # C2 : SUSPENDU ouvre automatiquement un ArretChantier, et la reprise le ferme
    if ancien_statut != StatutProjet.SUSPENDU and nouveau_statut == StatutProjet.SUSPENDU:
        from apps.projets.services.arret_chantier import declarer_arret_chantier

        declarer_arret_chantier(
            projet=projet,
            date_debut=timezone.localdate(),
            motif="Suspension du projet",
            auteur=utilisateur,
            commentaire="Arrêt ouvert automatiquement lors de la suspension du chantier.",
        )
    elif ancien_statut == StatutProjet.SUSPENDU and nouveau_statut != StatutProjet.SUSPENDU:
        arret_ouvert = projet.arrets_chantier.filter(
            supprime_le__isnull=True,
            date_fin__isnull=True,
        ).first()
        if arret_ouvert:
            from apps.projets.services.arret_chantier import terminer_arret_chantier

            terminer_arret_chantier(
                arret=arret_ouvert,
                date_fin=timezone.localdate(),
                utilisateur=utilisateur,
            )

    projet.statut = nouveau_statut
    projet.save(update_fields=["statut", "modifie_le"])

    if ancien_statut != nouveau_statut:
        from apps.projets.services.sante_declencheur import declencher_recalcul_sante

        declencher_recalcul_sante(
            projet_id=projet.id,
            declencheur_type="PROJET_STATUT_TRANSITION",
            declencheur_id=str(nouveau_statut),
        )

    return projet


def valider_transition_reception(projet: Projet) -> None:
    """Garde-fou d'intégrité absolu : valide l'éligibilité à la réception du projet.

    Lève une ValidationError si le projet contient au moins un lot actif non clôturé.
    """
    lots_actifs = projet.lots.filter(supprime_le__isnull=True)
    if not lots_actifs.exists():
        return

    lots_non_clotures = lots_actifs.exclude(
        models.Q(statut=StatutLot.CLOTURE) | models.Q(avancement=100)
    )

    if lots_non_clotures.exists():
        details = [
            f"{lot.code} - {lot.libelle} (Statut: {lot.statut}, Avancement: {lot.avancement}%)"
            for lot in lots_non_clotures
        ]
        msg = (
            "Impossible de réceptionner le projet : 100 % des lots doivent être clôturés. "
            f"Lots non clôturés ({len(details)}) : {', '.join(details)}."
        )
        logger.warning(
            "Refus de réception pour le projet %s (%s) : lots incomplets.",
            projet.id,
            projet.reference,
        )
        raise ValidationError({"statut": msg})


def retablir_statut_apres_decalage_si_necessaire(
    instance: Projet | Lot | Activite,
    nouvelle_date_fin: date,
    date_reference: date | None = None,
) -> bool:
    """Rétablit instantanément le statut EN_COURS si l'instance était en retard et que la date est repoussée.

    Retourne True si le statut a été rétabli, False sinon.
    """
    date_ref = date_reference or timezone.now().date()
    if nouvelle_date_fin < date_ref:
        return False

    statut_actuel = getattr(instance, "statut", None)

    if isinstance(instance, Projet):
        if statut_actuel == StatutProjet.EN_RETARD:
            instance.statut = StatutProjet.EN_COURS
            return True
    elif isinstance(instance, Lot):
        if statut_actuel == StatutLot.EN_RETARD:
            instance.statut = StatutLot.EN_COURS
            return True
    elif isinstance(instance, Activite):
        if statut_actuel == StatutActivite.EN_RETARD:
            instance.statut = StatutActivite.EN_COURS
            return True

    return False


@transaction.atomic
def executer_evaluation_quotidienne_schema(date_reference: date | None = None) -> dict:
    """Exécute l'évaluation quotidienne calendaire sur l'ensemble du schéma tenant courant.

    Traite la cascade ascendante : Activités -> Lots -> Projets.
    """
    date_ref = date_reference or timezone.now().date()
    nb_activites = 0
    nb_lots = 0
    nb_projets = 0

    # 1. Évaluation des activités
    activites = Activite.objects.filter(supprime_le__isnull=True).exclude(
        statut__in=[StatutActivite.CLOTURE, StatutActivite.SUSPENDU]
    )
    for act in activites.iterator():
        if evaluer_statut_activite(act, date_reference=date_ref):
            nb_activites += 1

    # 2. Évaluation des lots
    lots = Lot.objects.filter(supprime_le__isnull=True).exclude(
        statut__in=[StatutLot.CLOTURE, StatutLot.SUSPENDU]
    )
    for lot in lots.iterator():
        if evaluer_statut_lot(lot, date_reference=date_ref):
            nb_lots += 1

    # 3. Évaluation des projets
    projets = Projet.objects.filter(supprime_le__isnull=True).exclude(
        statut__in=STATUTS_PROJET_MANUELS_FIXES
    )
    for projet in projets.iterator():
        if evaluer_statut_projet(projet, date_reference=date_ref):
            nb_projets += 1

    return {
        "date_reference": date_ref.isoformat(),
        "activites_modifiees": nb_activites,
        "lots_modifies": nb_lots,
        "projets_modifies": nb_projets,
    }
