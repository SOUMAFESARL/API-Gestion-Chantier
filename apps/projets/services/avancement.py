"""Service de synchronisation d'avancement physique depuis les rapports de chantier (F3).

Lorsqu'un rapport journalier est approuvé, les mesures saisies (quantités réalisées, pourcentages
déclarés ou jalons atteints sur les feuilles de l'arbre) sont reportées sur les **feuilles**
concernées, puis l'avancement de toutes les cases et du projet est recalculé et stocké
(décisions v1.2, §9).
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from apps.chantier.models import JournalChantier, RapportJournalier
from apps.core.enums import StatutRapport
from apps.projets.models import Element, ModeMesure, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.alertes_retard import detecter_alertes_retard
from apps.projets.services.arbre import cloturer_si_objectif_atteint
from apps.projets.services.machine_etats import evaluer_statut_projet, evaluer_statuts_arbre
from apps.projets.services.sante_calculs import calculer_arbre, resultat_projet
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

logger = logging.getLogger(__name__)

__all__ = [
    "mesures_du_journal",
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
    """Recalcule et stocke le physique de toutes les cases actives, puis celui du projet."""
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

    from apps.projets.services.courbe import enregistrer_releve

    enregistrer_releve(projet, jour=timezone.localdate())


def mesures_du_journal(saisie: dict) -> dict[str, dict]:
    """Extrait les mesures du jour par feuille (`quantite`, `pourcentage`, `jalon`).

    Parcourt `activites` ainsi que l'historique `production`.
    """
    if not isinstance(saisie, dict):
        return {}
    mesures: dict[str, dict] = {}
    for section in ("activites", "production"):
        lignes = saisie.get(section) or []
        if not isinstance(lignes, list):
            continue
        for ligne in lignes:
            if not isinstance(ligne, dict):
                continue
            act_id = ligne.get("activite_id")
            if not act_id:
                continue
            cle = str(act_id)
            entree = mesures.setdefault(
                cle,
                {"quantite": Decimal("0"), "pourcentage": None, "jalon": False},
            )
            q_brut = ligne.get("quantite_jour")
            if q_brut is not None:
                try:
                    q_dec = Decimal(str(q_brut))
                    if q_dec.is_finite() and q_dec > Decimal("0"):
                        entree["quantite"] += q_dec
                except (ValueError, TypeError, InvalidOperation):
                    pass
            p_brut = ligne.get("pourcentage_jour")
            if p_brut is not None:
                try:
                    p_dec = Decimal(str(p_brut))
                    if p_dec.is_finite() and Decimal("0") <= p_dec <= Decimal("100"):
                        actuel = entree["pourcentage"]
                        entree["pourcentage"] = max(actuel, p_dec) if actuel is not None else p_dec
                except (ValueError, TypeError, InvalidOperation):
                    pass
            if bool(ligne.get("jalon_atteint")):
                entree["jalon"] = True
    return mesures


def quantites_du_journal(saisie: dict) -> dict[str, Decimal]:
    """Extrait la somme des quantités (> 0) du jour par feuille d'un journal."""
    return {
        act_id: m["quantite"]
        for act_id, m in mesures_du_journal(saisie).items()
        if m["quantite"] > Decimal("0")
    }


def quantites_synchronisees(projet) -> dict[str, Decimal]:
    """Somme des quantités déjà synchronisées par des journaux APPROUVE sur ce projet."""
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
    """Recalcule et propage l'avancement après mise à jour des mesures de feuilles."""
    if projet:
        projet_pk = getattr(projet, "pk", projet)
        projet = Projet.objects.select_for_update().get(pk=projet_pk)
        recalculer_avancements_projet(projet)
        evaluer_statuts_arbre(projet)
        evaluer_statut_projet(projet)
        declencher_recalcul_sante(
            projet_id=projet.pk,
            declencheur_type=declencheur_type,
            declencheur_id=declencheur_id,
        )
        detecter_alertes_retard(projet)


@transaction.atomic
def synchroniser_rapport_approuve(rapport_id: uuid.UUID | str) -> bool:
    """Synchronise les mesures (`QUANTITE`, `POURCENTAGE`, `JALON`) d'un rapport approuvé."""
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
    brut = mesures_du_journal(saisie)
    par_uuid: dict[uuid.UUID, dict] = {}
    for act_id_str, m in brut.items():
        try:
            act_uuid = (
                uuid.UUID(str(act_id_str)) if not isinstance(act_id_str, uuid.UUID) else act_id_str
            )
        except (ValueError, TypeError, AttributeError):
            continue
        par_uuid[act_uuid] = m

    feuilles_touchees = list(
        Element.objects.filter(
            pk__in=par_uuid.keys(), projet_id=rapport.projet_id, supprime_le__isnull=True
        )
        .select_for_update()
        .order_by("pk")
    )

    activites_modifiees = []
    for feuille in feuilles_touchees:
        m = par_uuid.get(feuille.pk)
        if not m:
            continue
        champs: list[str] = []
        mode = feuille.mode_mesure or ModeMesure.QUANTITE
        if mode == ModeMesure.POURCENTAGE:
            pct = m["pourcentage"]
            if pct is not None:
                actuel = feuille.pourcentage_declare or Decimal("0.00")
                nouveau = min(Decimal("100.00"), max(actuel, _arrondi(pct)))
                if nouveau > actuel or (
                    feuille.pourcentage_declare is None and nouveau > Decimal("0.00")
                ):
                    feuille.pourcentage_declare = nouveau
                    champs.append("pourcentage_declare")
        elif mode == ModeMesure.JALON:
            if m["jalon"] and not feuille.cloture:
                feuille.cloture = True
                feuille.cloture_le = timezone.now()
                champs.extend(["cloture", "cloture_le"])
                if not feuille.date_fin_reelle and rapport.date_rapport:
                    feuille.date_fin_reelle = rapport.date_rapport
                    champs.append("date_fin_reelle")
        else:
            q_ajoute = m["quantite"]
            if q_ajoute > Decimal("0"):
                q_actuelle = feuille.quantite_realisee or Decimal("0.000")
                feuille.quantite_realisee = q_actuelle + q_ajoute
                champs.append("quantite_realisee")

        # À 100 %, la feuille se clôt d'elle-même, au jour du rapport qui l'a menée là.
        if champs and cloturer_si_objectif_atteint(feuille, jour=rapport.date_rapport):
            champs.extend(["cloture", "cloture_le", "date_fin_reelle"])

        if champs:
            if feuille.date_debut_reelle is None and rapport.date_rapport:
                feuille.date_debut_reelle = rapport.date_rapport
                champs.append("date_debut_reelle")
            champs.append("modifie_le")
            feuille.save(update_fields=champs)
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

    if projet and rapport.date_rapport and rapport.date_rapport != timezone.localdate():
        from apps.projets.services.courbe import enregistrer_releve

        enregistrer_releve(projet, jour=rapport.date_rapport)

    RapportJournalier.objects.filter(pk=rapport.pk).update(f3_sync_done=True)

    return True
