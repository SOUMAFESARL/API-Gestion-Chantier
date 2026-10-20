"""Service de détection des alertes de retard et déduplication (F3).

Spécifications :
- SFD F3 v1.0 §5.4 (Vue Alertes et Retards Détectés)
- SFD F3 v1.0 §10 (Modèle AlerteRetard)
- RG-F3-07 (Détection retards — déduplication des alertes Celery)
- Erratum SFD F3 v1.0.1 (E-3, E-4)
- Tâches 147 (Causes & actions recommandées) et 148 (Déduplication seuils)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.chantier.models import Blocage
from apps.core.enums import RoleGlobal, RoleProjet, StatutBlocage, StatutRapport
from apps.projets.models import (
    AffectationProjet,
    AlerteRetard,
    Lot,
    NiveauAlerteRetard,
    Projet,
    StatutAlerteRetard,
)
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.sante_calculs import calculer_delta_lot

logger = logging.getLogger(__name__)

__all__ = [
    "ACTION_PAR_DEFAUT",
    "ORDRE_NIVEAUX",
    "TABLE_ACTIONS_RECOMMANDEES",
    "detecter_alertes_retard",
    "determiner_actions_recommandees",
    "extraire_causes_alerte",
    "obtenir_destinataires_alerte",
]

ORDRE_NIVEAUX: dict[str, int] = {
    NiveauAlerteRetard.MODERE: 1,
    NiveauAlerteRetard.ELEVE: 2,
    NiveauAlerteRetard.CRITIQUE: 3,
}

TABLE_ACTIONS_RECOMMANDEES: dict[str, str] = {
    "absences": "Renforcer l'effectif",
    "blocages_ouverts": "Lever les blocages ouverts",
    "incidents": "Analyser les incidents déclarés",
}

ACTION_PAR_DEFAUT: str = "Revoir le planning du lot avec le conducteur de travaux"


def extraire_causes_alerte(
    projet: Projet,
    lot: Lot | None,
    date_reference: date,
) -> dict[str, Any]:
    """Extrait les causes du retard depuis les rapports F2 et les blocages ouverts.

    Fenêtre des 7 derniers jours calendaires [date_reference - 6 jours, date_reference] comprise.
    Ne retient que les rapports SOUMIS ou APPROUVE non supprimés du projet.
    Si lot est fourni, ne retient que les rapports de ce lot ou ceux sans lot spécifique.
    Causes :
    - absences : somme des écarts (prevus - presents > 0) des lignes effectifs de saisie
    - blocages_ouverts : liste des titres des blocages OUVERT ou PRIS_EN_CHARGE
    - incidents : nombre total de lignes de saisie["incidents"]
    """
    date_debut_7j = date_reference - timedelta(days=6)

    rapports_qs = projet.rapports_journaliers.filter(
        supprime_le__isnull=True,
        statut__in=[StatutRapport.SOUMIS, StatutRapport.APPROUVE],
        date_rapport__gte=date_debut_7j,
        date_rapport__lte=date_reference,
    ).select_related("journal")

    if lot is not None:
        rapports_qs = rapports_qs.filter(Q(lot=lot) | Q(lot__isnull=True))

    absences_total = 0
    incidents_total = 0

    for rap in rapports_qs:
        try:
            journal = rap.journal
        except ObjectDoesNotExist:
            journal = None

        if journal and isinstance(journal.saisie, dict):
            # Absences : somme des écarts prevus - presents
            effectifs = journal.saisie.get("effectifs") or []
            if isinstance(effectifs, list):
                for ligne in effectifs:
                    if isinstance(ligne, dict):
                        prevus = ligne.get("prevus")
                        presents = ligne.get("presents")
                        if prevus is not None:
                            try:
                                prev_int = int(prevus)
                                pres_int = int(presents) if presents is not None else 0
                                ecart = prev_int - pres_int
                                if ecart > 0:
                                    absences_total += ecart
                            except (ValueError, TypeError):
                                pass

            # Incidents : nombre de lignes saisie["incidents"]
            incidents_list = journal.saisie.get("incidents") or []
            if isinstance(incidents_list, list):
                incidents_total += len(incidents_list)

    # Blocages actifs (OUVERT ou PRIS_EN_CHARGE)
    blocages_qs = Blocage.objects.filter(
        projet=projet,
        supprime_le__isnull=True,
        statut__in=[StatutBlocage.OUVERT, StatutBlocage.PRIS_EN_CHARGE],
    )
    if lot is not None:
        blocages_qs = blocages_qs.filter(Q(lot=lot) | Q(lot__isnull=True))

    blocages_ouverts = list(
        blocages_qs.order_by("ouvert_le", "cree_le").values_list("titre", flat=True)
    )

    return {
        "absences": absences_total,
        "blocages_ouverts": blocages_ouverts,
        "incidents": incidents_total,
    }


def determiner_actions_recommandees(causes: dict[str, Any]) -> list[str]:
    """Déduit les actions recommandées à partir du dictionnaire des causes."""
    actions: list[str] = []

    if causes.get("absences", 0) > 0:
        actions.append(TABLE_ACTIONS_RECOMMANDEES["absences"])

    if causes.get("blocages_ouverts"):
        actions.append(TABLE_ACTIONS_RECOMMANDEES["blocages_ouverts"])

    if causes.get("incidents", 0) > 0:
        actions.append(TABLE_ACTIONS_RECOMMANDEES["incidents"])

    if not actions:
        actions.append(ACTION_PAR_DEFAUT)

    return actions


def obtenir_destinataires_alerte(projet: Projet, niveau: str) -> list[Utilisateur]:
    """Détermine les destinataires de l'alerte selon son niveau de criticité.

    Règles (SFD F3 §5.4 & §3 Matrice des droits) :
    - MODERE   : CT et CP du projet (affectations actives ou rôles directs sur le projet)
    - ELEVE    : CT + CP + utilisateurs DO de l'entreprise
    - CRITIQUE : CT + CP + DO + Directeur Général (DG) de l'entreprise
    """
    destinataires: set[Utilisateur] = set()

    # 1. CT et CP du projet (inclus à tous les niveaux)
    if (
        projet.chef_projet_id
        and getattr(projet.chef_projet, "is_active", True)
        and getattr(projet.chef_projet, "supprime_le", None) is None
    ):
        destinataires.add(projet.chef_projet)

    if (
        projet.conducteur_travaux_id
        and getattr(projet.conducteur_travaux, "is_active", True)
        and getattr(projet.conducteur_travaux, "supprime_le", None) is None
    ):
        destinataires.add(projet.conducteur_travaux)

    affs = AffectationProjet.objects.filter(
        projet=projet,
        est_actif=True,
        supprime_le__isnull=True,
        role_projet__in=[
            RoleProjet.CONDUCTEUR_TRAVAUX,
            RoleProjet.CHEF_PROJET,
        ],
        utilisateur__supprime_le__isnull=True,
        utilisateur__is_active=True,
    ).select_related("utilisateur")
    for aff in affs:
        destinataires.add(aff.utilisateur)

    # 2. Utilisateurs DO de l'entreprise (pour ELEVE et CRITIQUE)
    if niveau in (NiveauAlerteRetard.ELEVE, NiveauAlerteRetard.CRITIQUE):
        dos = Utilisateur.objects.filter(
            supprime_le__isnull=True,
            is_active=True,
        ).filter(
            Q(role__code="DO") | Q(role_global="DO")
        )
        for u in dos:
            destinataires.add(u)

    # 3. Directeur Général (DG) de l'entreprise (pour CRITIQUE)
    if niveau == NiveauAlerteRetard.CRITIQUE:
        dgs = Utilisateur.objects.filter(
            supprime_le__isnull=True,
            is_active=True,
        ).filter(
            Q(is_owner=True)
            | Q(role__code="DG")
            | Q(role_global__in=[RoleGlobal.DIRECTEUR_GENERAL, "DG", "DIRECTEUR_GENERAL"])
        )
        for u in dgs:
            destinataires.add(u)

    return list(destinataires)


@transaction.atomic
def detecter_alertes_retard(
    projet: Projet,
    date_reference: date | None = None,
) -> list[AlerteRetard]:
    """Détecte les alertes de retard d'un projet et applique la déduplication RG-F3-07.

    (1) Calendrier d'entreprise construit UNE SEULE FOIS pour la période.
    Pour chaque lot actif non supprimé, calcule son delta temporel - physique.
    Niveaux selon settings.F3_SEUILS_RETARD_PTS :
      - delta > 25 pts -> CRITIQUE
      - delta > 15 pts -> ELEVE
      - delta > 5 pts  -> MODERE
      - sinon          -> aucun
    Au niveau du projet :
      - si projet.indice_sante n'est pas null et < settings.F3_SEUIL_INDICE_SANTE_CRITIQUE (40),
        le niveau est CRITIQUE (avec lot null).

    (2) Déduplication (RG-F3-07) :
    Une alerte n'est créée que si le niveau atteint est STRICTEMENT supérieur au plus haut
    niveau des alertes de ce lot (ou du projet) encore OUVERTE ou EN_COURS
    (ordre MODERE < ELEVE < CRITIQUE).
    Si aucune alerte n'est ouverte/en cours, tout niveau atteint en crée une.

    (3) Causes et actions recommandées :
    Remplies à partir des rapports F2 des 7 derniers jours et des blocages ouverts.

    (4) Destinataires :
    Rattachés selon le niveau de criticité (MODERE: CT+CP, ELEVE: +DO, CRITIQUE: +DG).

    Retourne la liste des instances AlerteRetard créées.
    """
    if isinstance(date_reference, datetime):
        date_ref = date_reference.date()
    elif date_reference is not None:
        date_ref = date_reference
    else:
        date_ref = timezone.localdate()

    # 1. Lecture dynamique des seuils dans les réglages
    seuil_modere = float(settings.F3_SEUILS_RETARD_PTS["MODERE"])
    seuil_eleve = float(settings.F3_SEUILS_RETARD_PTS["ELEVE"])
    seuil_critique = float(settings.F3_SEUILS_RETARD_PTS["CRITIQUE"])
    seuil_indice_sante = settings.F3_SEUIL_INDICE_SANTE_CRITIQUE

    # 2. Récupération des lots actifs non supprimés
    lots_actifs = list(
        projet.lots.filter(
            est_actif=True,
            supprime_le__isnull=True,
        ).prefetch_related("activites").order_by("code", "pk")
    )

    # 3. Construction UNIQUE du calendrier de l'entreprise
    dates_pertinentes: list[date] = [
        d
        for d in [
            getattr(projet, "date_debut_prevue", None),
            getattr(projet, "date_fin_prevue", None),
            getattr(projet, "date_debut_baseline", None),
            getattr(projet, "date_fin_baseline", None),
            getattr(projet, "date_debut_reelle", None),
            getattr(projet, "date_fin_reelle", None),
            date_ref,
        ]
        if d is not None
    ]
    for lot in lots_actifs:
        for d in [
            getattr(lot, "date_debut_prevue", None),
            getattr(lot, "date_fin_prevue", None),
            getattr(lot, "date_debut_baseline", None),
            getattr(lot, "date_fin_baseline", None),
        ]:
            if d is not None:
                dates_pertinentes.append(d)

    annee_min = min(d.year for d in dates_pertinentes) if dates_pertinentes else date_ref.year
    annee_max = max(d.year for d in dates_pertinentes) if dates_pertinentes else date_ref.year
    calendrier = calendrier_entreprise(date(annee_min - 1, 1, 1), date(annee_max + 1, 12, 31))

    alertes_creees: list[AlerteRetard] = []

    # 4. Évaluation des alertes par lot
    for lot in lots_actifs:
        delta = calculer_delta_lot(lot, date_ref, calendrier)
        if delta is None:
            continue

        niveau_lot: str | None = None
        if delta > seuil_critique:
            niveau_lot = NiveauAlerteRetard.CRITIQUE
        elif delta > seuil_eleve:
            niveau_lot = NiveauAlerteRetard.ELEVE
        elif delta > seuil_modere:
            niveau_lot = NiveauAlerteRetard.MODERE

        if not niveau_lot:
            continue

        # Déduplication RG-F3-07 pour ce lot
        alertes_ouvertes = AlerteRetard.objects.filter(
            projet=projet,
            lot=lot,
            statut__in=[StatutAlerteRetard.OUVERTE, StatutAlerteRetard.EN_COURS],
            supprime_le__isnull=True,
        )
        max_rang_ouvert = max(
            [ORDRE_NIVEAUX.get(a.niveau, 0) for a in alertes_ouvertes],
            default=0,
        )

        rang_atteint = ORDRE_NIVEAUX.get(niveau_lot, 0)
        if rang_atteint <= max_rang_ouvert:
            # Niveau non strictement supérieur à l'alerte encore ouverte
            continue

        causes = extraire_causes_alerte(projet, lot, date_ref)
        actions = determiner_actions_recommandees(causes)
        destinataires = obtenir_destinataires_alerte(projet, niveau_lot)

        alerte = AlerteRetard.objects.create(
            projet=projet,
            lot=lot,
            niveau=niveau_lot,
            delta_pts=Decimal(str(round(delta, 2))),
            indice_sante=None,
            date_detection=date_ref,
            statut=StatutAlerteRetard.OUVERTE,
            causes=causes,
            actions_recommandees=actions,
        )
        if destinataires:
            alerte.destinataires.set(destinataires)

        alertes_creees.append(alerte)

    # 5. Évaluation de l'alerte au niveau du projet (indice de santé critique)
    if projet.indice_sante is not None and projet.indice_sante < seuil_indice_sante:
        niveau_projet = NiveauAlerteRetard.CRITIQUE

        alertes_ouvertes_projet = AlerteRetard.objects.filter(
            projet=projet,
            lot__isnull=True,
            statut__in=[StatutAlerteRetard.OUVERTE, StatutAlerteRetard.EN_COURS],
            supprime_le__isnull=True,
        )
        max_rang_ouvert_proj = max(
            [ORDRE_NIVEAUX.get(a.niveau, 0) for a in alertes_ouvertes_projet],
            default=0,
        )

        rang_projet = ORDRE_NIVEAUX.get(niveau_projet, 0)
        if rang_projet > max_rang_ouvert_proj:
            causes_proj = extraire_causes_alerte(projet, None, date_ref)
            actions_proj = determiner_actions_recommandees(causes_proj)
            destinataires_proj = obtenir_destinataires_alerte(projet, niveau_projet)

            alerte_proj = AlerteRetard.objects.create(
                projet=projet,
                lot=None,
                niveau=niveau_projet,
                delta_pts=None,
                indice_sante=projet.indice_sante,
                date_detection=date_ref,
                statut=StatutAlerteRetard.OUVERTE,
                causes=causes_proj,
                actions_recommandees=actions_proj,
            )
            if destinataires_proj:
                alerte_proj.destinataires.set(destinataires_proj)

            alertes_creees.append(alerte_proj)

    return alertes_creees
