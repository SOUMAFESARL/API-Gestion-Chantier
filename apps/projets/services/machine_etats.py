"""Service d'orchestration de la machine à états et d'évaluation quotidienne des chantiers.

Schéma : tenant.
Module CDC : 1 (Gestion des Projets) & 2 (Suivi Technique des Travaux).
Conformité : SFD F3 §7 (Statuts automatiques de projet).

Invariants garantis :
1. Transitions automatiques de projet (SFD F3 §7) :
   - EN_ATTENTE -> EN_COURS dès que date_du_jour >= date_debut_prevue (ou réelle)
     ET qu'au moins un rapport F2 a été soumis (SOUMIS ou APPROUVE).
   - EN_COURS / EN_RETARD -> CRITIQUE dès qu'une case suivie (niveau coché « alerter ») présente
     un delta de retard > F3_SEUILS_RETARD_PTS["CRITIQUE"] (25 pts)
     OU que projet.indice_sante < F3_SEUIL_INDICE_SANTE_CRITIQUE (40).
   - EN_COURS -> EN_RETARD dès qu'une case suivie présente un delta de retard
     > F3_SEUILS_RETARD_PTS["MODERE"] (5 pts).
   - Règle de retour SFD §7 : un projet CRITIQUE qui ne l'est plus repasse obligatoirement
     par EN_RETARD (jamais directement EN_COURS). Il ne rejoindra EN_COURS qu'à une
     évaluation ultérieure.
2. Rétablissement instantané en temps réel :
   - EN_RETARD -> EN_COURS dès qu'un décalage justifié (reprogrammation de date)
     repousse la date de fin à une date >= date_du_jour.
3. Verrou absolu de Réception :
   - Aucun projet ne peut passer à RECEPTIONNE (ou TERMINE) tant qu'une feuille active de son
     arbre n'est pas clôturée (ou à 100 %).
4. Préservation des états manuels et terminaux (puits stables) :
   - Les statuts SUSPENDU, BLOQUE, DESACTIVE, RESILIE, ARCHIVE, RECEPTIONNE et TERMINE
     (STATUTS_PROJET_MANUELS_FIXES) ne sont jamais écrasés automatiquement par la tâche nocturne.
     Le statut CRITIQUE est quant à lui automatique (SFD F3 §7) et non protégé.
"""

import logging
from datetime import date

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.enums import StatutActivite, StatutProjet, StatutRapport
from apps.projets.models import Element, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.sante_calculs import (
    calculer_arbre,
    calculer_delta_element,
    calculer_deltas_arbre,
)

logger = logging.getLogger(__name__)

__all__ = [
    "STATUTS_ACHEVES",
    "STATUTS_FIN_DE_VIE",
    "STATUTS_PROJET_MANUELS_FIXES",
    "ProjetClosError",
    "cases_suivies",
    "changer_statut_projet",
    "evaluer_statut_projet",
    "evaluer_statuts_arbre",
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
            detail=(
                "Le projet est achevé (réceptionné ou terminé). "
                "Cette opération n'est plus autorisée."
            ),
            code="projet_clos",
        )


def cases_suivies(arbre) -> list:
    """Les cases sur lesquelles le retard se juge : celles des niveaux cochés « alerter à ce
    niveau » (§13quater-ter) ; à défaut de niveau coché, les racines. Jamais un libellé."""
    return arbre.niveaux_alerte() or [r for r in arbre.racines() if r.est_actif]


def _calendrier_autour(date_ref, *dates):
    connues = [d for d in (*dates, date_ref) if d is not None]
    annee_min = min(min(connues).year, date_ref.year - 1)
    annee_max = max(max(connues).year, date_ref.year + 1)
    return calendrier_entreprise(date(annee_min, 1, 1), date(annee_max, 12, 31))


def evaluer_statuts_arbre(projet: Projet, date_reference: date | None = None) -> int:
    """Le statut de chaque case, **jugée sur elle-même** (décisions v1.2, §10).

    | Situation                                              | Statut    |
    | La case ou un de ses ancêtres est suspendu             | Suspendu  |
    | Feuille clôturée ; parent dont tous les enfants le sont | Clôturé   |
    | Fin prévue dépassée, ou écart au-delà du seuil         | En retard |
    | Commencée, ou date de début atteinte                   | En cours  |
    | Sinon                                                  | Planifié  |

    Un enfant en retard ne met pas son parent en retard. Rend le nombre de cases modifiées.
    """
    date_ref = date_reference or timezone.localdate()
    arbre = charger_arbre(projet)
    if not arbre.elements:
        return 0
    resultats = calculer_arbre(arbre)
    calendrier = _calendrier_autour(
        date_ref, projet.date_debut_prevue, projet.date_fin_prevue
    )
    seuil = settings.F3_SEUILS_RETARD_PTS["MODERE"]
    statuts: dict = {}

    def cloture(element) -> bool:
        if element.pk in statuts:
            return statuts[element.pk] == StatutActivite.CLOTURE
        enfants = arbre.enfants_actifs(element)
        if not enfants:
            return element.cloture
        return all(cloture(e) for e in enfants)

    a_jour = []
    for element in arbre.elements:
        if not element.est_actif:
            continue
        if arbre.suspendu(element):
            nouveau = StatutActivite.SUSPENDU
        elif cloture(element):
            nouveau = StatutActivite.CLOTURE
        else:
            resultat = resultats.get(element.pk)
            physique = resultat.physique if resultat and resultat.physique is not None else 0.0
            ecart = calculer_delta_element(element, date_ref, calendrier, physique)
            fin_depassee = bool(element.date_fin_prevue and date_ref > element.date_fin_prevue)
            if fin_depassee or (ecart is not None and ecart > seuil):
                nouveau = StatutActivite.EN_RETARD
            elif arbre.commence(element) or (
                element.date_debut_prevue and date_ref >= element.date_debut_prevue
            ):
                nouveau = StatutActivite.EN_COURS
            else:
                nouveau = StatutActivite.PLANIFIE
        statuts[element.pk] = nouveau
        if element.statut != nouveau:
            element.statut = nouveau
            a_jour.append(element)
    if a_jour:
        Element.objects.bulk_update(a_jour, ["statut"])
    return len(a_jour)


def evaluer_statut_projet(projet: Projet, date_reference: date | None = None) -> bool:
    """Évalue et met à jour le statut d'un projet selon la SFD F3 §7.

    Règles de passage et transitions :
    1. Préservation absolue des statuts manuels et terminaux (STATUTS_PROJET_MANUELS_FIXES).
    2. EN_ATTENTE reste EN_ATTENTE tant que la date de début n'est pas atteinte OU
       qu'aucun rapport F2 n'a été soumis (SOUMIS ou APPROUVE), puis passe EN_COURS.
    3. Pour un projet démarré, calcule le delta de chaque case suivie (`cases_suivies`,
       calendrier de l'entreprise construit UNE fois) et l'indice (projet.indice_sante).
       - CRITIQUE si une case a un delta > F3_SEUILS_RETARD_PTS["CRITIQUE"] (25 pts)
         OU si l'indice est < F3_SEUIL_INDICE_SANTE_CRITIQUE (40).
       - EN_RETARD si une case a un delta > F3_SEUILS_RETARD_PTS["MODERE"] (5 pts).
       - EN_COURS sinon.
    4. RÈGLE DE RETOUR : un projet CRITIQUE qui ne l'est plus repasse EN_RETARD,
       jamais directement EN_COURS. Il ne rejoindra EN_COURS qu'à une évaluation suivante.
    5. En cas de changement : journalisation et déclenchement du recalcul de santé réactif.

    Retourne True si le statut a été modifié et sauvegardé, False sinon.
    """
    date_ref = date_reference or timezone.localdate()

    if projet.statut in STATUTS_PROJET_MANUELS_FIXES:
        return False

    if projet.statut == StatutProjet.EN_ATTENTE:
        date_debut = projet.date_debut_prevue or getattr(projet, "date_debut_reelle", None)
        debut_atteint = bool(date_debut and date_ref >= date_debut)
        rapport_soumis = projet.rapports_journaliers.filter(
            supprime_le__isnull=True,
            statut__in=[StatutRapport.SOUMIS, StatutRapport.APPROUVE],
        ).exists()
        if not (debut_atteint and rapport_soumis):
            return False
        nouveau_statut = StatutProjet.EN_COURS
    else:
        # Projet démarré : le retard se juge sur les cases suivies, avec un seul calendrier.
        calendrier = _calendrier_autour(
            date_ref,
            getattr(projet, "date_debut_prevue", None),
            getattr(projet, "date_fin_prevue", None),
            getattr(projet, "date_debut_reelle", None),
            getattr(projet, "date_fin_reelle", None),
        )
        arbre = charger_arbre(projet)
        resultats = calculer_arbre(arbre)
        par_case = calculer_deltas_arbre(arbre, resultats, date_ref, calendrier)
        deltas: list[float] = [
            d for d in (par_case.get(case.pk) for case in cases_suivies(arbre)) if d is not None
        ]

        seuil_critique_pts = settings.F3_SEUILS_RETARD_PTS["CRITIQUE"]
        seuil_modere_pts = settings.F3_SEUILS_RETARD_PTS["MODERE"]
        seuil_critique_indice = settings.F3_SEUIL_INDICE_SANTE_CRITIQUE

        lot_critique = any(d > seuil_critique_pts for d in deltas)
        indice_critique = (
            projet.indice_sante is not None
            and projet.indice_sante < seuil_critique_indice
        )
        lot_en_retard = any(d > seuil_modere_pts for d in deltas)

        if lot_critique or indice_critique:
            nouveau_statut = StatutProjet.CRITIQUE
        elif lot_en_retard:
            nouveau_statut = StatutProjet.EN_RETARD
        else:
            if projet.statut == StatutProjet.CRITIQUE:
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

    Lève une ValidationError tant qu'une feuille active de l'arbre n'est ni clôturée ni à 100 %.
    """
    arbre = charger_arbre(projet)
    feuilles = arbre.feuilles()
    if not feuilles:
        return
    resultats = calculer_arbre(arbre)
    non_cloturees = [
        f
        for f in feuilles
        if not f.cloture and (resultats.get(f.pk) is None or resultats[f.pk].physique != 100.0)
    ]
    if non_cloturees:
        details = [" / ".join(arbre.chemin_libelles(f)) for f in non_cloturees[:20]]
        msg = (
            "Impossible de réceptionner le projet : toutes les tâches doivent être clôturées. "
            f"Tâches non clôturées ({len(non_cloturees)}) : {', '.join(details)}."
        )
        logger.warning(
            "Refus de réception pour le projet %s (%s) : tâches incomplètes.",
            projet.id,
            projet.reference,
        )
        raise ValidationError({"statut": msg})


def retablir_statut_apres_decalage_si_necessaire(
    instance: Projet | Element,
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
    elif isinstance(instance, Element):
        if statut_actuel == StatutActivite.EN_RETARD:
            instance.statut = StatutActivite.EN_COURS
            return True

    return False


@transaction.atomic
def executer_evaluation_quotidienne_schema(date_reference: date | None = None) -> dict:
    """Exécute l'évaluation quotidienne calendaire sur l'ensemble du schéma tenant courant :
    les cases de chaque arbre, puis les projets."""
    date_ref = date_reference or timezone.now().date()
    nb_cases = 0
    nb_projets = 0

    projets = Projet.objects.filter(supprime_le__isnull=True)
    for projet in projets.iterator():
        nb_cases += evaluer_statuts_arbre(projet, date_reference=date_ref)

    for projet in projets.exclude(statut__in=STATUTS_PROJET_MANUELS_FIXES).iterator():
        if evaluer_statut_projet(projet, date_reference=date_ref):
            nb_projets += 1

    return {
        "date_reference": date_ref.isoformat(),
        "cases_modifiees": nb_cases,
        "projets_modifies": nb_projets,
    }
