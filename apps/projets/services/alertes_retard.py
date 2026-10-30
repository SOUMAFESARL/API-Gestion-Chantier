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
from apps.core.enums import StatutBlocage, StatutRapport
from apps.projets.models import (
    AlerteRetard,
    Element,
    ModeMesure,
    NiveauAlerteRetard,
    Projet,
    StatutAlerteRetard,
)
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.sante_calculs import (
    calculer_arbre,
    calculer_delta_element,
    calculer_deltas_arbre,
)

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

ACTION_PAR_DEFAUT: str = "Revoir le planning de cette partie avec le conducteur de travaux"


def extraire_causes_alerte(
    projet: Projet,
    element: Element | None,
    date_reference: date,
) -> dict[str, Any]:
    """Extrait les causes du retard depuis les rapports F2 et les blocages ouverts.

    Fenêtre des 7 derniers jours calendaires [date_reference - 6 jours, date_reference] comprise.
    Ne retient que les rapports SOUMIS ou APPROUVE non supprimés du projet.
    Le journal est tenu par projet et par jour : tous ses rapports comptent, quelle que soit
    la case. Les blocages, eux, se rattachent à une case : ceux de la case, de ses descendants
    et ceux sans case.
    Causes :
    - absences : somme des écarts (prevus - presents > 0) des lignes effectifs de saisie,
      plus les membres d'équipe non cochés présents
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

            # Absences par équipe : les membres du jour (figés à la soumission) non cochés.
            membres = {
                e["equipe_id"]: len(e.get("membres", []))
                for e in (journal.photographie or {}).get("equipes", [])
                if isinstance(e, dict)
            }
            for ligne in journal.saisie.get("equipes") or []:
                if isinstance(ligne, dict) and ligne.get("equipe_id") in membres:
                    absences_total += max(
                        0, membres[ligne["equipe_id"]] - len(ligne.get("presents") or [])
                    )

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
    if element is not None:
        blocages_qs = blocages_qs.filter(
            Q(element__chemin__startswith=element.chemin) | Q(element__isnull=True)
        )

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


#: La permission de chaque niveau, du plus bas au plus haut (30/10/2026).
PERMISSIONS_ALERTE = (
    (NiveauAlerteRetard.MODERE, "projets.alertes_moderees"),
    (NiveauAlerteRetard.ELEVE, "projets.alertes_elevees"),
    (NiveauAlerteRetard.CRITIQUE, "projets.alertes_critiques"),
)


def permissions_recevant(niveau: str) -> set[str]:
    """Une permission d'alerte vaut « à partir de ce niveau » : qui reçoit les alertes modérées
    reçoit aussi les élevées et les critiques — comme le conducteur et le chef de projet avant."""
    codes = [code for _, code in PERMISSIONS_ALERTE]
    rang = next(i for i, (n, _) in enumerate(PERMISSIONS_ALERTE) if n == niveau)
    return set(codes[: rang + 1])


def obtenir_destinataires_alerte(projet: Projet, niveau: str, element=None) -> list[Utilisateur]:
    """Ceux qui ont la permission de recevoir les alertes de ce niveau (30/10/2026).

    - **Sur le projet** : les personnes affectées dont le rôle sur le projet porte la permission,
      et dont la partie du projet recouvre la case en retard (toute la partie pour une alerte
      du projet entier).
    - **Dans l'entreprise** : les rôles de portée Entreprise qui portent la permission, et le DG,
      qui les a toutes.

    Le nom du rôle ne compte pas : l'entreprise règle ces permissions sur ses rôles.
    """
    from apps.chantier.services.fonctions import titulaires
    from apps.core.droits import permissions_effectives
    from apps.projets.services.perimetres import _acces_entreprise

    codes = permissions_recevant(niveau)
    chemins_case = (element.chemin,) if element is not None else ()
    destinataires: dict = {}
    for code in codes:
        for titulaire in titulaires(projet, code):
            if titulaire.concerne(chemins_case):
                destinataires[titulaire.utilisateur.pk] = titulaire.utilisateur
    for utilisateur in Utilisateur.objects.filter(
        supprime_le__isnull=True, is_active=True
    ).select_related("role"):
        # Portée Entreprise ou DG : leurs permissions valent sur tous les projets.
        if utilisateur.pk in destinataires or not _acces_entreprise(utilisateur):
            continue
        if codes & set(permissions_effectives(utilisateur)):
            destinataires[utilisateur.pk] = utilisateur
    return list(destinataires.values())


@transaction.atomic
def detecter_alertes_retard(
    projet: Projet,
    date_reference: date | None = None,
) -> list[AlerteRetard]:
    """Détecte les alertes de retard d'un projet et applique la déduplication RG-F3-07.

    (1) Calendrier d'entreprise construit UNE SEULE FOIS pour la période.
    Pour chaque case suivie (niveau coché « alerter »), calcule son delta temporel - physique.
    Niveaux selon settings.F3_SEUILS_RETARD_PTS :
      - delta > 25 pts -> CRITIQUE
      - delta > 15 pts -> ELEVE
      - delta > 5 pts  -> MODERE
      - sinon          -> aucun
    Au niveau du projet :
      - si projet.indice_sante n'est pas null et < settings.F3_SEUIL_INDICE_SANTE_CRITIQUE (40),
        le niveau est CRITIQUE (sans case).

    (2) Déduplication (RG-F3-07) :
    Une alerte n'est créée que si le niveau atteint est STRICTEMENT supérieur au plus haut
    niveau des alertes de cette case (ou du projet) encore OUVERTE ou EN_COURS
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

    # 2. Les cases suivies : niveaux cochés « alerter à ce niveau », à défaut les racines.
    #    Une alerte par problème : les feuilles en retard en dessous en sont les causes.
    from apps.projets.services.machine_etats import cases_suivies

    arbre = charger_arbre(projet)
    resultats = calculer_arbre(arbre)
    suivies = sorted(cases_suivies(arbre), key=lambda c: (c.chemin, c.pk))

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
    for case in arbre.elements:
        for d in [case.date_debut_prevue, case.date_fin_prevue]:
            if d is not None:
                dates_pertinentes.append(d)
    annee_min = min(d.year for d in dates_pertinentes) if dates_pertinentes else date_ref.year
    annee_max = max(d.year for d in dates_pertinentes) if dates_pertinentes else date_ref.year
    calendrier = calendrier_entreprise(date(annee_min - 1, 1, 1), date(annee_max + 1, 12, 31))

    def physique(case):
        r = resultats.get(case.pk)
        return r.physique if r and r.physique is not None else 0.0

    alertes_creees: list[AlerteRetard] = []
    deltas = calculer_deltas_arbre(arbre, resultats, date_ref, calendrier)

    # 4. Évaluation des alertes par case suivie
    for case in suivies:
        delta = deltas.get(case.pk)
        if delta is None:
            continue

        niveau_case: str | None = None
        if delta > seuil_critique:
            niveau_case = NiveauAlerteRetard.CRITIQUE
        elif delta > seuil_eleve:
            niveau_case = NiveauAlerteRetard.ELEVE
        elif delta > seuil_modere:
            niveau_case = NiveauAlerteRetard.MODERE

        if not niveau_case:
            continue

        # Déduplication RG-F3-07 pour cette case
        alertes_ouvertes = AlerteRetard.objects.filter(
            projet=projet,
            element=case,
            statut__in=[StatutAlerteRetard.OUVERTE, StatutAlerteRetard.EN_COURS],
            supprime_le__isnull=True,
        )
        max_rang_ouvert = max(
            [ORDRE_NIVEAUX.get(a.niveau, 0) for a in alertes_ouvertes],
            default=0,
        )
        rang_atteint = ORDRE_NIVEAUX.get(niveau_case, 0)
        if rang_atteint <= max_rang_ouvert:
            continue

        causes = extraire_causes_alerte(projet, case, date_ref)
        # Les feuilles en retard sous la case, classées par leur poids dans le retard
        # (montant x écart), plutôt qu'une alerte chacune (§13quater-ter).
        en_retard = []
        for feuille in arbre.descendants(case) or [case]:
            if not feuille.est_actif or not arbre.est_feuille(feuille):
                continue
            ecart = calculer_delta_element(feuille, date_ref, calendrier, physique(feuille))
            if ecart is not None and ecart > seuil_modere:
                en_retard.append((float(feuille.montant or 0) * ecart, feuille.libelle))
        causes["taches_en_retard"] = [libelle for _, libelle in sorted(en_retard, reverse=True)]
        actions = determiner_actions_recommandees(causes)
        destinataires = obtenir_destinataires_alerte(projet, niveau_case, case)

        alerte = AlerteRetard.objects.create(
            projet=projet,
            element=case,
            niveau=niveau_case,
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

    # 4 bis. Un jalon manqué alerte toujours (30/10/2026) : sa date est passée et il n'est pas
    #        atteint. Niveau élevé, quel que soit l'écart, et sur le jalon lui-même.
    for feuille in arbre.feuilles():
        jour_jalon = feuille.date_fin_prevue or feuille.date_debut_prevue
        if (
            feuille.mode_mesure != ModeMesure.JALON
            or feuille.cloture
            or arbre.suspendu(feuille)
            or not jour_jalon
            or jour_jalon >= date_ref
        ):
            continue
        ouvertes = AlerteRetard.objects.filter(
            projet=projet,
            element=feuille,
            statut__in=[StatutAlerteRetard.OUVERTE, StatutAlerteRetard.EN_COURS],
            supprime_le__isnull=True,
        )
        rang_ouvert = max([ORDRE_NIVEAUX.get(x.niveau, 0) for x in ouvertes], default=0)
        if ORDRE_NIVEAUX.get(NiveauAlerteRetard.ELEVE, 0) <= rang_ouvert:
            continue
        causes = {
            "jalon_manque": feuille.libelle,
            "date_jalon": jour_jalon.isoformat(),
            "jours_de_retard": (date_ref - jour_jalon).days,
        }
        alerte = AlerteRetard.objects.create(
            projet=projet,
            element=feuille,
            niveau=NiveauAlerteRetard.ELEVE,
            delta_pts=None,
            indice_sante=None,
            date_detection=date_ref,
            statut=StatutAlerteRetard.OUVERTE,
            causes=causes,
            actions_recommandees=[
                "Vérifier si le jalon est atteint et le déclarer, ou replanifier sa date."
            ],
        )
        destinataires = obtenir_destinataires_alerte(projet, NiveauAlerteRetard.ELEVE, feuille)
        if destinataires:
            alerte.destinataires.set(destinataires)
        alertes_creees.append(alerte)

    # 5. Évaluation de l'alerte au niveau du projet (indice de santé critique)
    if projet.indice_sante is not None and projet.indice_sante < seuil_indice_sante:
        niveau_projet = NiveauAlerteRetard.CRITIQUE

        alertes_ouvertes_projet = AlerteRetard.objects.filter(
            projet=projet,
            element__isnull=True,
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
                element=None,
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
