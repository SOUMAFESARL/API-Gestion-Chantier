"""Service de synchronisation d'avancement physique depuis les rapports de chantier (F3).

Lorsqu'un rapport journalier est approuvé, les quantités réalisées saisies (lignes « activites »
et « production » du journal) sont reportées sur les **feuilles** de l'arbre concernées, puis
l'avancement de toutes les cases et du projet est recalculé et stocké (décisions v1.2, §9).

Le contrat JSON du journal garde ses clés (`activite_id`, `lot_id`) : une « activité » y est une
feuille de l'arbre, un « lot » la case qui la regroupe (`Arbre.groupe`).
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.chantier.models import JournalChantier, RapportJournalier
from apps.core.enums import StatutRapport
from apps.projets.models import Element, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.alertes_retard import detecter_alertes_retard
from apps.projets.services.machine_etats import evaluer_statut_projet
from apps.projets.services.sante_calculs import calculer_arbre, resultat_projet
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

logger = logging.getLogger(__name__)

__all__ = [
    "quantites_du_journal",
    "quantites_synchronisees",
    "recalculer_apres_quantites",
    "recalculer_avancements_projet",
    "synchroniser_rapport_approuve",
]


def _arrondi(valeur):
    if valeur is None:
        return None
    return Decimal(str(valeur)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recalculer_avancements_projet(projet) -> None:
    """Recalcule et stocke le physique de toutes les cases actives, puis celui du projet.

    Un projet compte quelques centaines de cases : tout recalculer coûte moins cher que de
    remonter la chaîne d'ancêtres de chaque feuille touchée, et ne laisse aucun parent en retard
    d'un calcul. Une case dont l'avancement est indisponible garde `None`.
    """
    arbre = charger_arbre(projet)
    resultats = calculer_arbre(arbre)
    a_jour = []
    for element in arbre.elements:
        resultat = resultats.get(element.pk)
        nouveau = _arrondi(resultat.physique) if resultat else None
        if element.avancement != nouveau:
            element.avancement = nouveau
            a_jour.append(element)
    if a_jour:
        Element.objects.bulk_update(a_jour, ["avancement"])
    resultat = resultat_projet(projet, arbre, resultats)
    projet.avancement_reel = _arrondi(resultat.physique) or Decimal("0.00")
    projet.save(update_fields=["avancement_reel"])


def quantites_du_journal(saisie: dict) -> dict[str, Decimal]:
    """Extrait la somme des quantités du jour par activité d'un journal.

    Parcourt les sections 'activites' et 'production'. Ne retient que les
    lignes dont l'identifiant d'activité est renseigné et dont la quantite_jour
    est non nulle, convertible en Decimal et strictement positive (> 0).
    Retourne un dictionnaire {activite_id_str: somme_decimal}.
    """
    if not isinstance(saisie, dict):
        return {}
    cumuls: dict[str, Decimal] = {}
    for section in ("activites", "production"):
        lignes = saisie.get(section) or []
        if not isinstance(lignes, list):
            continue
        for ligne in lignes:
            if not isinstance(ligne, dict):
                continue
            q_brut = ligne.get("quantite_jour")
            if q_brut is None:
                continue
            try:
                q_dec = Decimal(str(q_brut))
                if not q_dec.is_finite() or q_dec <= Decimal("0"):
                    continue
            except (ValueError, TypeError, InvalidOperation):
                continue
            act_id = ligne.get("activite_id")
            if not act_id:
                continue
            cle = str(act_id)
            cumuls[cle] = cumuls.get(cle, Decimal("0")) + q_dec
    return cumuls


def quantites_synchronisees(projet) -> dict[str, Decimal]:
    """Calcule la somme des quantités synchronisées sur toutes les activités du projet.

    Ne prend en compte que les JournalChantier du projet dont le rapport est
    statut=APPROUVE, f3_sync_done=True et non supprimé (rapport__supprime_le__isnull=True).
    Retourne un dictionnaire {activite_id_str: total_decimal}.
    """
    journaux = JournalChantier.objects.filter(
        rapport__projet=projet,
        rapport__statut=StatutRapport.APPROUVE,
        rapport__f3_sync_done=True,
        rapport__supprime_le__isnull=True,
    ).only("saisie")

    cumuls: dict[str, Decimal] = {}
    for journal in journaux:
        q_journal = quantites_du_journal(journal.saisie or {})
        for act_id, q_dec in q_journal.items():
            cumuls[act_id] = cumuls.get(act_id, Decimal("0")) + q_dec
    return cumuls


def recalculer_apres_quantites(
    activites,
    projet=None,
    declencheur_type: str = "RAPPORT_APPROBATION",
    declencheur_id: uuid.UUID | str | None = None,
) -> None:
    """Recalcule et propage l'avancement après mise à jour des quantités réalisées.

    Chaîne de recalcul (F3) partagée entre l'approbation de rapport et la mise à jour inline :
    1. Recalcule et enregistre le physique de toutes les cases et du projet.
    2. Réévalue le statut du projet via machine d'états.
    3. Déclenche le recalcul réactif de l'indice de santé.
    4. Détecte les alertes de retard du projet.

    Rien ne s'exécute sans ``projet`` : il n'est jamais déduit des feuilles.
    """
    if projet:
        projet_pk = getattr(projet, "pk", projet)
        projet = Projet.objects.select_for_update().get(pk=projet_pk)
        recalculer_avancements_projet(projet)

        evaluer_statut_projet(projet)

        declencher_recalcul_sante(
            projet_id=projet.pk,
            declencheur_type=declencheur_type,
            declencheur_id=declencheur_id,
        )

        detecter_alertes_retard(projet)


@transaction.atomic
def synchroniser_rapport_approuve(rapport_id: uuid.UUID | str) -> bool:
    """Synchronise les quantités d'un rapport approuvé avec l'avancement physique.

    Étapes :
    1. Verrouille le rapport (select_for_update). Si non APPROUVE ou f3_sync_done, rend False.
    2. Lit le journal associé (si absent, marque f3_sync_done et rend True).
    3. Cumule les quantite_jour > 0 des lignes d'activités et de production.
    4. Met à jour quantite_realisee des feuilles trouvées (du projet, non supprimées).
    5. Recalcule et stocke l'avancement de l'arbre et du projet.
    6. Marque f3_sync_done=True sur le rapport par update de queryset (évite post_save).
    7. Déclenche le recalcul réactif de l'indice de santé (RAPPORT_APPROBATION).
    8. Réévalue le statut du projet puis détecte les alertes de retard (F3).

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
        if rapport.projet_id:
            projet = Projet.objects.filter(pk=rapport.projet_id).first()
            if projet:
                evaluer_statut_projet(projet)
                detecter_alertes_retard(projet)
        return True

    saisie = journal.saisie or {}
    quantites = quantites_du_journal(saisie)
    cumuls: dict[uuid.UUID, Decimal] = {}
    for act_id_str, q_dec in quantites.items():
        try:
            act_uuid = (
                uuid.UUID(str(act_id_str))
                if not isinstance(act_id_str, uuid.UUID)
                else act_id_str
            )
        except (ValueError, TypeError, AttributeError):
            continue
        cumuls[act_uuid] = q_dec

    feuilles_touchees = list(
        Element.objects.filter(
            pk__in=cumuls.keys(), projet_id=rapport.projet_id, supprime_le__isnull=True
        )
        .select_for_update()
        .order_by("pk")
    )

    activites_modifiees = []
    for feuille in feuilles_touchees:
        q_ajoute = cumuls.get(feuille.pk, Decimal("0"))
        if q_ajoute > Decimal("0"):
            q_actuelle = feuille.quantite_realisee or Decimal("0.000")
            feuille.quantite_realisee = q_actuelle + q_ajoute
            feuille.save(update_fields=["quantite_realisee", "modifie_le"])
            activites_modifiees.append(feuille)

    projet = None
    if rapport.projet_id:
        projet = Projet.objects.select_for_update().get(pk=rapport.projet_id)

    recalculer_apres_quantites(
        activites=activites_modifiees,
        projet=projet,
        declencheur_type="RAPPORT_APPROBATION",
        declencheur_id=rapport.pk,
    )

    RapportJournalier.objects.filter(pk=rapport.pk).update(f3_sync_done=True)

    return True
