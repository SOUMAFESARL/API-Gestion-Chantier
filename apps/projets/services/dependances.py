"""Les dépendances entre tâches (décisions v1.2, §13quinquies.5 ; décisions du 30/10/2026).

**Un seul type de lien : B commence après la fin de A.**

- Plusieurs prédécesseurs par tâche ; un lien relie deux **feuilles** actives du même projet,
  d'une même branche ou de deux branches ; **sans délai** ; **les boucles sont refusées**.
- « Après la fin » : B commence **au plus tôt le lendemain** de la fin prévue de A (une date de
  fin est un jour travaillé jusqu'au soir). Une tâche sans dates ne contraint rien.
- **Planifier B avant la fin d'un de ses prédécesseurs est refusé** (`dependance_non_respectee`),
  avec un message qui nomme ce prédécesseur.
- **Reprogrammer A** : les successeurs qui commenceraient trop tôt sont listés
  (`successeurs_a_decaler`) ; seuls ceux que l'on confirme sont décalés, durée conservée, en
  suivant les règles des dates (§11 : le parent encadre, prolongation sous `projets.prolonger`).
  Jamais de décalage silencieux : un successeur non confirmé refuse la reprogrammation.
- **Détailler** une feuille liée (ou lui ajouter des sous-tâches) : chaque nouvelle feuille hérite
  de ses prédécesseurs, et ses successeurs attendent toutes les nouvelles feuilles.
- **Désactiver** (ou supprimer) une case retire les liens des feuilles de sa branche, tracé au
  journal d'audit.

Créer ou retirer un lien exige `projets.planifier` dans le périmètre des deux feuilles (vues).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.projets.models import Dependance, Element
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier import formater_date

__all__ = [
    "BoucleDependances",
    "Decalage",
    "DependanceNonRespectee",
    "SuccesseursADecaler",
    "ajouter_lien",
    "appliquer_decalages",
    "date_debut_au_plus_tot",
    "decalages_necessaires",
    "liens_de_la_case",
    "liens_par_case",
    "retirer_lien",
    "retirer_liens_branche",
    "transferer_liens_aux_feuilles",
    "verifier_predecesseurs",
]


class DependanceNonRespectee(ErreurMetier):
    code_metier = "dependance_non_respectee"
    default_detail = "Cette tâche commencerait avant la fin d'un de ses prédécesseurs."


class SuccesseursADecaler(ErreurMetier):
    """Le report ferait commencer des successeurs trop tôt : l'écran les liste, « décaler aussi »
    coché par défaut, et l'on confirme par `decaler_successeurs`."""

    code_metier = "successeurs_a_decaler"
    default_detail = (
        "Ce report ferait commencer des tâches qui la suivent avant sa fin : confirmez leur "
        "décalage, ou choisissez d'autres dates."
    )


class BoucleDependances(ErreurConflit):
    code_metier = "dependance_boucle"
    default_detail = "Ce lien fermerait une boucle : une tâche finirait par se suivre elle-même."


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def _liens(projet):
    return list(
        Dependance.objects.filter(projet=projet).only(
            "id", "predecesseur_id", "successeur_id", "projet_id"
        )
    )


def _graphe(liens):
    successeurs, predecesseurs = defaultdict(list), defaultdict(list)
    for lien in liens:
        successeurs[lien.predecesseur_id].append(lien.successeur_id)
        predecesseurs[lien.successeur_id].append(lien.predecesseur_id)
    return successeurs, predecesseurs


def respectee(predecesseur, successeur) -> bool | None:
    """Vrai si B commence après la fin de A ; None si l'une des deux dates manque."""
    if not predecesseur.date_fin_prevue or not successeur.date_debut_prevue:
        return None
    return successeur.date_debut_prevue > predecesseur.date_fin_prevue


def _case_en_dict(case, lien, visible: bool) -> dict:
    donnees = {"lien_id": str(lien.pk), "id": str(case.pk), "visible": visible}
    if visible:
        donnees.update(
            {
                "libelle": case.libelle,
                "date_debut_prevue": case.date_debut_prevue,
                "date_fin_prevue": case.date_fin_prevue,
            }
        )
    return donnees


def liens_par_case(arbre, acces: dict | None = None) -> dict:
    """`{case_id: {"predecesseurs": [...], "successeurs": [...]}}` pour tout le projet, en une
    requête. Une case liée hors de la vue de la personne n'est donnée que par son identifiant."""
    resultat: dict = defaultdict(lambda: {"predecesseurs": [], "successeurs": []})
    for lien in _liens(arbre.projet):
        a, b = arbre.par_id.get(lien.predecesseur_id), arbre.par_id.get(lien.successeur_id)
        if a is None or b is None:
            continue
        ok = respectee(a, b)
        vue_a = acces is None or acces.get(a.pk) == "COMPLET"
        vue_b = acces is None or acces.get(b.pk) == "COMPLET"
        resultat[b.pk]["predecesseurs"].append({**_case_en_dict(a, lien, vue_a), "respectee": ok})
        resultat[a.pk]["successeurs"].append({**_case_en_dict(b, lien, vue_b), "respectee": ok})
    return resultat


def liens_de_la_case(element, acces: dict | None = None) -> dict:
    arbre = charger_arbre(element.projet)
    liens = liens_par_case(arbre, acces).get(element.pk)
    return liens or {"predecesseurs": [], "successeurs": []}


# --------------------------------------------------------------------------
# La règle : B commence après la fin de A
# --------------------------------------------------------------------------
def date_debut_au_plus_tot(feuille, fins: dict | None = None):
    """Le lendemain de la fin la plus tardive de ses prédécesseurs (actifs et datés), ou None.

    `fins` remplace la fin de certaines cases (simulation d'un report)."""
    fins = fins or {}
    plus_tard = None
    bloquant = None
    for lien in Dependance.objects.filter(successeur=feuille).select_related("predecesseur"):
        predecesseur = lien.predecesseur
        if not predecesseur.est_actif:
            continue
        fin = fins.get(predecesseur.pk, predecesseur.date_fin_prevue)
        if fin and (plus_tard is None or fin > plus_tard):
            plus_tard, bloquant = fin, predecesseur
    if plus_tard is None:
        return None, None
    return plus_tard + timedelta(days=1), bloquant


def verifier_predecesseurs(feuille, debut: date | None) -> None:
    """Refuse un début avant la fin d'un prédécesseur, en le nommant."""
    if not debut:
        return
    au_plus_tot, predecesseur = date_debut_au_plus_tot(feuille)
    if au_plus_tot and debut < au_plus_tot:
        raise DependanceNonRespectee(
            f"« {feuille.libelle} » ne peut pas commencer le {formater_date(debut)} : elle suit "
            f"« {predecesseur.libelle} », qui finit le "
            f"{formater_date(predecesseur.date_fin_prevue)}. Elle commence au plus tôt le "
            f"{formater_date(au_plus_tot)}.",
            details={
                "predecesseur": {
                    "id": str(predecesseur.pk),
                    "libelle": predecesseur.libelle,
                    "date_fin_prevue": predecesseur.date_fin_prevue,
                },
                "date_debut_au_plus_tot": au_plus_tot,
            },
        )


# --------------------------------------------------------------------------
# Reprogrammer A : décaler ses successeurs
# --------------------------------------------------------------------------
@dataclass
class Decalage:
    """Un successeur qui commencerait trop tôt, et les dates qu'il prendrait s'il est décalé."""

    cible: Element
    debut_avant: date
    fin_avant: date | None
    debut_apres: date
    fin_apres: date | None
    apres: Element  # le prédécesseur qui impose la nouvelle date

    def en_dict(self) -> dict:
        return {
            "id": str(self.cible.pk),
            "libelle": self.cible.libelle,
            "date_debut_avant": self.debut_avant,
            "date_fin_avant": self.fin_avant,
            "date_debut_apres": self.debut_apres,
            "date_fin_apres": self.fin_apres,
            "jours": (self.debut_apres - self.debut_avant).days,
            "apres": {"id": str(self.apres.pk), "libelle": self.apres.libelle},
            "decaler_aussi": True,
        }


def decalages_necessaires(element, nouvelle_fin: date | None) -> list[Decalage]:
    """Les successeurs (de proche en proche) qui commenceraient trop tôt si `element` finissait
    le `nouvelle_fin`, et les dates qu'ils prendraient décalés, durée conservée."""
    if not nouvelle_fin:
        return []
    liens = _liens(element.projet)
    if not liens:
        return []
    successeurs, predecesseurs = _graphe(liens)
    cases = {
        e.pk: e
        for e in Element.objects.filter(
            pk__in={i for lien in liens for i in (lien.predecesseur_id, lien.successeur_id)}
        )
    }
    debuts = {pk: c.date_debut_prevue for pk, c in cases.items()}
    fins = {pk: c.date_fin_prevue for pk, c in cases.items()}
    fins[element.pk] = nouvelle_fin
    decalages: dict = {}
    a_voir = [element.pk]
    while a_voir:
        courant = a_voir.pop(0)
        for suivant in successeurs.get(courant, []):
            case = cases[suivant]
            if not case.est_actif or not debuts[suivant]:
                continue
            fin_imposee, imposee_par = None, None
            for p in predecesseurs[suivant]:
                if (
                    cases[p].est_actif
                    and fins[p]
                    and (fin_imposee is None or fins[p] > fin_imposee)
                ):
                    fin_imposee, imposee_par = fins[p], cases[p]
            if fin_imposee is None:
                continue
            au_plus_tot = fin_imposee + timedelta(days=1)
            if debuts[suivant] >= au_plus_tot:
                continue
            duree = (fins[suivant] - debuts[suivant]) if fins[suivant] else None
            if suivant not in decalages:
                decalages[suivant] = Decalage(
                    cible=case,
                    debut_avant=case.date_debut_prevue,
                    fin_avant=case.date_fin_prevue,
                    debut_apres=au_plus_tot,
                    fin_apres=None,
                    apres=imposee_par,
                )
            decalage = decalages[suivant]
            decalage.debut_apres, decalage.apres = au_plus_tot, imposee_par
            decalage.fin_apres = au_plus_tot + duree if duree is not None else None
            debuts[suivant], fins[suivant] = decalage.debut_apres, decalage.fin_apres
            a_voir.append(suivant)
    return list(decalages.values())


def appliquer_decalages(
    element,
    nouvelle_fin: date | None,
    *,
    decaler_successeurs,
    autorise,
    motif,
    justification: str,
    prolonger: bool = False,
    auteur=None,
) -> list[dict]:
    """Décale les successeurs confirmés ; refuse si un successeur à décaler ne l'est pas.

    `decaler_successeurs` : identifiants confirmés (None : rien n'a été confirmé).
    `autorise(code, case)` : la permission s'exerce-t-elle sur cette case (périmètre) ?
    Chaque décalage est une reprogrammation du successeur : historique des dates avec le motif
    du report d'origine, prolongation de ses parents selon le §11, trace au journal d'audit.
    """
    from apps.projets.models import TypeObjetHistorique
    from apps.projets.services.reprogrammation import (
        _appliquer_prolongations,
        _tracer,
    )

    decalages = decalages_necessaires(element, nouvelle_fin)
    if not decalages:
        return []
    confirmes = {str(i) for i in (decaler_successeurs or [])}
    oublies = [d for d in decalages if str(d.cible.pk) not in confirmes]
    if decaler_successeurs is None or oublies:
        cites = oublies or decalages
        noms = ", ".join(f"« {d.cible.libelle} »" for d in cites)
        raise SuccesseursADecaler(
            f"Ce report ferait commencer {noms} avant la fin d'une tâche qui "
            + (
                "la précède : confirmez son décalage"
                if len(cites) == 1
                else "les précède : confirmez leur décalage"
            )
            + ", ou choisissez d'autres dates.",
            details={
                "successeurs": [d.en_dict() for d in decalages],
                "non_confirmes": [str(d.cible.pk) for d in oublies or decalages],
            },
        )
    if motif is None:
        raise ValidationError(
            {"motif_id": "Décaler les tâches qui suivent est un report : le motif est requis."}
        )
    resultats = []
    for decalage in decalages:
        cible = Element.objects.get(pk=decalage.cible.pk)
        if not autorise("projets.planifier", cible):
            raise PermissionDenied(
                f"Décaler « {cible.libelle} » exige la permission « projets.planifier » sur "
                "cette tâche : elle n'est pas dans votre périmètre."
            )
        justif = f"Décalée par le report de « {element.libelle} » : {justification}"
        prolongations = _appliquer_prolongations(
            cible,
            decalage.debut_apres,
            decalage.fin_apres,
            prolonger=prolonger,
            autorise_a_prolonger=autorise("projets.prolonger", cible),
            motif=motif,
            justification=justif,
            auteur=auteur,
        )
        for champ, avant, apres in (
            ("date_debut_prevue", cible.date_debut_prevue, decalage.debut_apres),
            ("date_fin_prevue", cible.date_fin_prevue, decalage.fin_apres),
        ):
            _tracer(cible, TypeObjetHistorique.ELEMENT, champ, avant, apres, motif, justif, auteur)
        cible.date_debut_prevue = decalage.debut_apres
        cible.date_fin_prevue = decalage.fin_apres
        cible.save(update_fields=["date_debut_prevue", "date_fin_prevue", "modifie_le"])
        _tracer_audit(
            cible,
            auteur,
            "DECALAGE_SUCCESSEUR",
            avant={
                "date_debut_prevue": _iso(decalage.debut_avant),
                "date_fin_prevue": _iso(decalage.fin_avant),
            },
            apres={
                "date_debut_prevue": _iso(decalage.debut_apres),
                "date_fin_prevue": _iso(decalage.fin_apres),
                "apres": str(decalage.apres.pk),
            },
            motif=justification,
        )
        resultats.append({**decalage.en_dict(), "prolongations": prolongations})
    return resultats


def _iso(valeur):
    return valeur.isoformat() if valeur else None


def _tracer_audit(element, auteur, evenement, avant=None, apres=None, motif=""):
    from apps.projets.services.arbre import _tracer

    _tracer(element, auteur, evenement, avant=avant, apres=apres, motif=motif)


# --------------------------------------------------------------------------
# Ajouter, retirer un lien
# --------------------------------------------------------------------------
def _chemin_vers(depart, arrivee, successeurs) -> list | None:
    """Un chemin de `depart` à `arrivee` en suivant les liens, ou None."""
    pile, vus = [(depart, [depart])], {depart}
    while pile:
        courant, chemin = pile.pop()
        if courant == arrivee:
            return chemin
        for suivant in successeurs.get(courant, []):
            if suivant not in vus:
                vus.add(suivant)
                pile.append((suivant, [*chemin, suivant]))
    return None


@transaction.atomic
def ajouter_lien(predecesseur: Element, successeur: Element, *, auteur=None) -> Dependance:
    """« B commence après la fin de A » entre deux feuilles actives du même projet."""
    if predecesseur.projet_id != successeur.projet_id:
        raise ErreurMetier("Deux tâches de projets différents ne se lient pas.")
    if predecesseur.pk == successeur.pk:
        raise ErreurMetier("Une tâche ne se suit pas elle-même.")
    arbre = charger_arbre(predecesseur.projet)
    a, b = arbre.par_id[predecesseur.pk], arbre.par_id[successeur.pk]
    for case in (a, b):
        if not case.est_actif or any(not x.est_actif for x in arbre.ancetres(case)):
            raise ErreurMetier(f"« {case.libelle} » est désactivée : elle ne se lie plus.")
        if not arbre.est_feuille(case):
            raise ErreurMetier(
                f"« {case.libelle} » a des sous-tâches : les dépendances relient des tâches du "
                "bas (des feuilles)."
            )
    liens = _liens(arbre.projet)
    if any(x.predecesseur_id == a.pk and x.successeur_id == b.pk for x in liens):
        raise ErreurConflit(f"« {b.libelle} » suit déjà « {a.libelle} ».")
    successeurs, _ = _graphe(liens)
    boucle = _chemin_vers(b.pk, a.pk, successeurs)
    if boucle is not None:
        noms = " → ".join(f"« {arbre.par_id[i].libelle} »" for i in [*boucle, b.pk])
        raise BoucleDependances(
            f"Ce lien fermerait une boucle : {noms}.",
            details={"boucle": [str(i) for i in [*boucle, b.pk]]},
        )
    if respectee(a, b) is False:
        au_plus_tot = a.date_fin_prevue + timedelta(days=1)
        raise DependanceNonRespectee(
            f"« {b.libelle} » commence le {formater_date(b.date_debut_prevue)}, avant la fin de "
            f"« {a.libelle} » ({formater_date(a.date_fin_prevue)}) : reprogrammez-la au "
            f"{formater_date(au_plus_tot)} ou plus tard avant de les lier.",
            details={
                "predecesseur": {
                    "id": str(a.pk),
                    "libelle": a.libelle,
                    "date_fin_prevue": a.date_fin_prevue,
                },
                "date_debut_au_plus_tot": au_plus_tot,
            },
        )
    try:
        lien = Dependance.objects.create(
            projet=a.projet, predecesseur=a, successeur=b, cree_par=auteur
        )
    except IntegrityError:
        raise ErreurConflit(f"« {b.libelle} » suit déjà « {a.libelle} ».") from None
    _tracer_audit(b, auteur, "LIEN_AJOUT", apres={"predecesseur": str(a.pk), "lien": str(lien.pk)})
    _tracer_audit(a, auteur, "LIEN_AJOUT", apres={"successeur": str(b.pk), "lien": str(lien.pk)})
    return lien


@transaction.atomic
def retirer_lien(lien: Dependance, *, auteur=None) -> None:
    lien.delete(utilisateur=auteur)
    _tracer_audit(
        lien.successeur,
        auteur,
        "LIEN_RETRAIT",
        avant={"predecesseur": str(lien.predecesseur_id), "lien": str(lien.pk)},
    )
    _tracer_audit(
        lien.predecesseur,
        auteur,
        "LIEN_RETRAIT",
        avant={"successeur": str(lien.successeur_id), "lien": str(lien.pk)},
    )


# --------------------------------------------------------------------------
# Ce que les autres gestes font aux liens
# --------------------------------------------------------------------------
def retirer_liens_branche(element, *, auteur=None, evenement: str) -> int:
    """Désactiver ou supprimer une case retire les liens des tâches de sa branche (tracé)."""
    ids = list(
        Element.objects.filter(
            projet=element.projet, chemin__startswith=element.chemin
        ).values_list("pk", flat=True)
    )
    liens = list(
        Dependance.objects.filter(projet=element.projet).filter(
            Q(predecesseur_id__in=ids) | Q(successeur_id__in=ids)
        )
    )
    for lien in liens:
        lien.delete(utilisateur=auteur)
    if liens:
        _tracer_audit(
            element,
            auteur,
            evenement,
            avant={
                "liens": [
                    {
                        "lien": str(x.pk),
                        "predecesseur": str(x.predecesseur_id),
                        "successeur": str(x.successeur_id),
                    }
                    for x in liens
                ]
            },
        )
    return len(liens)


def transferer_liens_aux_feuilles(ancienne_feuille, *, auteur=None) -> int:
    """Une feuille liée devient un parent (détail, ajout de sous-tâches, copie dessous).

    Chaque nouvelle feuille de sa branche hérite de ses prédécesseurs, et ses successeurs
    attendent toutes les nouvelles feuilles ; les anciens liens sont retirés (ils relieraient
    un parent). Les dates des nouvelles feuilles doivent respecter leurs prédécesseurs hérités.
    """
    liens = list(
        Dependance.objects.filter(projet=ancienne_feuille.projet).filter(
            Q(predecesseur=ancienne_feuille) | Q(successeur=ancienne_feuille)
        )
    )
    if not liens:
        return 0
    arbre = charger_arbre(ancienne_feuille.projet)
    feuilles = [
        d
        for d in arbre.descendants(arbre.par_id[ancienne_feuille.pk])
        if d.est_actif and arbre.est_feuille(d)
    ]
    if not feuilles:
        return 0
    crees = []
    for lien in liens:
        lien.delete(utilisateur=auteur)
    for lien in liens:
        for feuille in feuilles:
            if lien.successeur_id == ancienne_feuille.pk:
                paire = (lien.predecesseur_id, feuille.pk)
            else:
                paire = (feuille.pk, lien.successeur_id)
            if Dependance.objects.filter(predecesseur_id=paire[0], successeur_id=paire[1]).exists():
                continue
            crees.append(
                Dependance.objects.create(
                    projet=ancienne_feuille.projet,
                    predecesseur_id=paire[0],
                    successeur_id=paire[1],
                    cree_par=auteur,
                )
            )
    successeurs = {x.successeur for x in liens if x.predecesseur_id == ancienne_feuille.pk}
    for feuille in [*feuilles, *successeurs]:
        verifier_predecesseurs(feuille, feuille.date_debut_prevue)
    _tracer_audit(
        ancienne_feuille,
        auteur,
        "LIENS_HERITES_DETAIL",
        avant={"liens": [str(x.pk) for x in liens]},
        apres={
            "feuilles": [str(f.pk) for f in feuilles],
            "liens": [
                {"predecesseur": str(x.predecesseur_id), "successeur": str(x.successeur_id)}
                for x in crees
            ],
        },
    )
    return len(crees)
