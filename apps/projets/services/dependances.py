"""Les dépendances entre tâches (décisions v1.2, §13quinquies.5 ; amendement 25/11/2026).

Quatre types de lien pris en charge (compatibles MS Project MSPDI) :
- `FS` (défaut) : Fin → Début (B commence après la fin de A ; tolérance même jour si A est jalon).
- `SS` : Début → Début (B commence au plus tôt au début de A).
- `FF` : Fin → Fin (B finit au plus tôt à la fin de A).
- `SF` : Début → Fin (B finit au plus tôt au début de A).

Chaque lien porte un décalage signé en **jours ouvrés** (`decalage_jours`, défaut `0` : positif =
attente / séchage, négatif = avance / chevauchement), calculé selon le calendrier de l'entreprise
(`calendrier_entreprise` : semaine type, jours fériés nationaux, exceptions).

- Plusieurs prédécesseurs par tâche ; un lien relie deux **feuilles** actives du même projet,
  d'une même branche ou de deux branches ; **les boucles sont refusées**.
- Une tâche sans les dates requises par le lien ne contraint rien (`respectee` rend `None`).
- **Planifier ou reprogrammer B** en violation d'un prédécesseur est refusé
  (`dependance_non_respectee`), avec un message nommant ce prédécesseur.
- **Reprogrammer A** : les successeurs impactés sont listés (`successeurs_a_decaler`) ; seuls
  ceux confirmés sont décalés, **durée ouvrée conservée**, en suivant les règles des dates (§11).
- **Détailler** une feuille liée transfère ses liens aux nouvelles feuilles en conservant
  `type_lien` et `decalage_jours`.
- **Désactiver** ou **supprimer** une case retire les liens des feuilles de sa branche, tracé au
  journal d'audit.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.contexte import entreprise_courante_id
from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.projets.models import Dependance, Element, ModeMesure, TypeDependance
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier import formater_date
from apps.projets.services.calendrier_ouvre import (
    CALENDRIER_PAR_DEFAUT_SEMAINE,
    Calendrier,
    calendrier_entreprise,
)
from apps.projets.services.sante_calculs import compter_jours_ouvres

__all__ = [
    "BoucleDependances",
    "Decalage",
    "DependanceNonRespectee",
    "SuccesseursADecaler",
    "ajouter_lien",
    "appliquer_decalages",
    "compter_duree_ouvree",
    "date_cible_fs",
    "date_debut_au_plus_tot",
    "decalages_necessaires",
    "decaler_jours_ouvres",
    "fin_apres_duree_ouvree",
    "liens_de_la_case",
    "liens_par_case",
    "prochain_jour_ouvre",
    "respectee",
    "retirer_lien",
    "retirer_liens_branche",
    "transferer_liens_aux_feuilles",
    "verifier_predecesseurs",
]

_NON_FOURNI = object()


class DependanceNonRespectee(ErreurMetier):
    code_metier = "dependance_non_respectee"
    default_detail = _("Les dates de cette tâche ne respectent pas l'un de ses prédécesseurs.")


class SuccesseursADecaler(ErreurMetier):
    """Le report impacte des successeurs : l'écran les liste, « décaler aussi »
    coché par défaut, et l'on confirme par `decaler_successeurs`."""

    code_metier = "successeurs_a_decaler"
    default_detail = _(
        "Ce report impacte des tâches qui la suivent : confirmez leur décalage, "
        "ou choisissez d'autres dates."
    )


class BoucleDependances(ErreurConflit):
    code_metier = "dependance_boucle"
    default_detail = _("Ce lien fermerait une boucle : une tâche finirait par se suivre elle-même.")


# --------------------------------------------------------------------------
# Arithmétique en jours ouvrés (calendrier d'entreprise)
# --------------------------------------------------------------------------
def _calendrier_effectif(
    dates: Iterable[date | None],
    calendrier: Calendrier | None = None,
    decalage_jours: int = 0,
) -> Calendrier:
    """Rend `calendrier` s'il est fourni, sinon le calendrier d'entreprise couvrant `dates`."""
    if calendrier is not None:
        return calendrier
    valides = [d for d in dates if d is not None]
    marge = max(365, abs(int(decalage_jours or 0)) * 2 + 90)
    if valides:
        d_min = min(valides) - timedelta(days=marge)
        d_max = max(valides) + timedelta(days=marge)
    else:
        aujourd_hui = date.today()
        d_min = aujourd_hui - timedelta(days=marge)
        d_max = aujourd_hui + timedelta(days=marge)
    if entreprise_courante_id() is not None:
        return calendrier_entreprise(d_min, d_max)
    return Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )


def prochain_jour_ouvre(d: date, cal: Calendrier) -> date:
    """Premier jour ouvré à partir de `d` (`d` lui-même s'il est ouvré)."""
    if not cal.jours_semaine:
        return d
    courant = d
    for _etape in range(4000):
        if cal.est_ouvre(courant):
            return courant
        courant += timedelta(days=1)
    return d


def _jour_ouvre_precedent(d: date, cal: Calendrier) -> date:
    """Dernier jour ouvré inférieur ou égal à `d` (`d` lui-même s'il est ouvré)."""
    if not cal.jours_semaine:
        return d
    courant = d
    for _etape in range(4000):
        if cal.est_ouvre(courant):
            return courant
        courant -= timedelta(days=1)
    return d


def decaler_jours_ouvres(d: date, n: int, cal: Calendrier) -> date:
    """Décale `d` de `n` jours ouvrés (`n > 0` avance, `n < 0` recule, `n == 0` inchangé)."""
    if n == 0:
        return d
    if not cal.jours_semaine:
        return d + timedelta(days=n)
    pas = timedelta(days=1) if n > 0 else timedelta(days=-1)
    restants = abs(n)
    courant = d
    limite = restants * 10 + 4000
    for _etape in range(limite):
        courant += pas
        if cal.est_ouvre(courant):
            restants -= 1
            if restants == 0:
                return courant
    return d + timedelta(days=n)


def compter_duree_ouvree(debut: date, fin: date, cal: Calendrier) -> int:
    """Nombre de jours ouvrés dans `[debut, fin]` (bornes incluses)."""
    if fin < debut:
        return 0
    return compter_jours_ouvres(debut, fin, cal)


def fin_apres_duree_ouvree(debut: date, duree_ouvree: int, cal: Calendrier) -> date:
    """Date de fin incluse d'une tâche débutant le `debut` pour `duree_ouvree` jours ouvrés."""
    if duree_ouvree <= 0:
        return debut
    depart = prochain_jour_ouvre(debut, cal)
    if duree_ouvree == 1:
        return depart
    return decaler_jours_ouvres(depart, duree_ouvree - 1, cal)


def _debut_avant_duree_ouvree(fin: date, duree_ouvree: int, cal: Calendrier) -> date:
    """Date de début incluse d'une tâche finissant le `fin` pour `duree_ouvree` jours ouvrés."""
    if duree_ouvree <= 0:
        return fin
    arrivee = _jour_ouvre_precedent(fin, cal)
    if duree_ouvree == 1:
        return arrivee
    return decaler_jours_ouvres(arrivee, -(duree_ouvree - 1), cal)


def date_cible_fs(
    fin_predecesseur: date,
    decalage_jours: int,
    cal: Calendrier,
    *,
    est_jalon: bool = False,
) -> date:
    """Date de début minimale d'un successeur lié en `FS` avec `decalage_jours` jours ouvrés.

    - Jalon prédécesseur : base = `fin_predecesseur` (même jour si `decalage_jours == 0`),
      décalé de `decalage_jours` jours ouvrés.
    - Tâche normale : base = prochain jour ouvré strictement après `fin_predecesseur`,
      puis décalé de `decalage_jours` jours ouvrés (`> 0` attente, `< 0` avance/chevauchement).
    """
    if est_jalon:
        return decaler_jours_ouvres(fin_predecesseur, decalage_jours, cal)
    base = decaler_jours_ouvres(fin_predecesseur, 1, cal)
    return decaler_jours_ouvres(base, decalage_jours, cal)


# --------------------------------------------------------------------------
# Accesseurs uniformes (Element ou nœud d'analyse MS Project)
# --------------------------------------------------------------------------
def _est_jalon(case) -> bool:
    return getattr(case, "mode_mesure", None) == ModeMesure.JALON or bool(
        getattr(case, "est_jalon", False)
    )


def _debut_case(case) -> date | None:
    if hasattr(case, "date_debut_prevue"):
        return case.date_debut_prevue
    return getattr(case, "debut", None)


def _fin_case(case) -> date | None:
    if hasattr(case, "date_fin_prevue"):
        return case.date_fin_prevue
    return getattr(case, "fin", None)


def _normaliser_type_lien(type_lien: str | None) -> str:
    code = (type_lien or TypeDependance.FS).strip().upper()
    if code not in TypeDependance.values:
        raise ValidationError(
            {"type_lien": _("Type de dépendance invalide (attendu : FS, SS, FF ou SF).")}
        )
    return code


def _libelle_lien(type_lien: str, decalage_jours: int) -> str:
    if decalage_jours > 0:
        return f"{type_lien} +{decalage_jours} j"
    if decalage_jours < 0:
        return f"{type_lien} {decalage_jours} j"
    return type_lien


# --------------------------------------------------------------------------
# Lecture & évaluation d'un lien
# --------------------------------------------------------------------------
def _liens(projet):
    return list(
        Dependance.objects.filter(projet=projet).only(
            "id",
            "predecesseur_id",
            "successeur_id",
            "projet_id",
            "type_lien",
            "decalage_jours",
        )
    )


def _graphe(liens):
    successeurs, predecesseurs = defaultdict(list), defaultdict(list)
    for lien in liens:
        successeurs[lien.predecesseur_id].append(lien.successeur_id)
        predecesseurs[lien.successeur_id].append(lien.predecesseur_id)
    return successeurs, predecesseurs


def _lien_respecte_dates(
    *,
    pred_est_jalon: bool,
    a_debut: date | None,
    a_fin: date | None,
    b_debut: date | None,
    b_fin: date | None,
    type_lien: str = TypeDependance.FS,
    decalage_jours: int = 0,
    calendrier: Calendrier | None = None,
) -> bool | None:
    """Évalue la conformité d'un lien à partir de ses dates brutes."""
    code = (type_lien or TypeDependance.FS).upper()
    decalage = int(decalage_jours or 0)

    if code == TypeDependance.FS:
        if a_fin is None or b_debut is None:
            return None
        if decalage == 0:
            if pred_est_jalon:
                return b_debut >= a_fin
            return b_debut > a_fin
        cal = _calendrier_effectif([a_fin, b_debut], calendrier, decalage)
        cible = date_cible_fs(a_fin, decalage, cal, est_jalon=pred_est_jalon)
        return b_debut >= cible

    if code == TypeDependance.SS:
        if a_debut is None or b_debut is None:
            return None
        if decalage == 0:
            return b_debut >= a_debut
        cal = _calendrier_effectif([a_debut, b_debut], calendrier, decalage)
        return b_debut >= decaler_jours_ouvres(a_debut, decalage, cal)

    if code == TypeDependance.FF:
        if a_fin is None or b_fin is None:
            return None
        if decalage == 0:
            return b_fin >= a_fin
        cal = _calendrier_effectif([a_fin, b_fin], calendrier, decalage)
        return b_fin >= decaler_jours_ouvres(a_fin, decalage, cal)

    if code == TypeDependance.SF:
        if a_debut is None or b_fin is None:
            return None
        if decalage == 0:
            return b_fin >= a_debut
        cal = _calendrier_effectif([a_debut, b_fin], calendrier, decalage)
        return b_fin >= decaler_jours_ouvres(a_debut, decalage, cal)

    return None


def respectee(
    predecesseur,
    successeur=None,
    type_lien: str = TypeDependance.FS,
    decalage_jours: int = 0,
    calendrier: Calendrier | None = None,
) -> bool | None:
    """Vrai si la dépendance entre A et B est respectée ; None si une date requise manque.

    Compatible avec :
    - `respectee(lien)` (objet `Dependance`) ;
    - `respectee(a, b)` (défaut `FS`, décalage `0`) ;
    - `respectee(a, b, type_lien=..., decalage_jours=..., calendrier=...)`.
    """
    if successeur is None and isinstance(predecesseur, Dependance):
        lien = predecesseur
        predecesseur = lien.predecesseur
        successeur = lien.successeur
        type_lien = lien.type_lien
        decalage_jours = lien.decalage_jours

    if predecesseur is None or successeur is None:
        return None

    return _lien_respecte_dates(
        pred_est_jalon=_est_jalon(predecesseur),
        a_debut=_debut_case(predecesseur),
        a_fin=_fin_case(predecesseur),
        b_debut=_debut_case(successeur),
        b_fin=_fin_case(successeur),
        type_lien=type_lien,
        decalage_jours=decalage_jours,
        calendrier=calendrier,
    )


def _case_en_dict(case, lien, visible: bool) -> dict:
    donnees = {
        "lien_id": str(lien.pk),
        "id": str(case.pk),
        "visible": visible,
        "type_lien": lien.type_lien,
        "decalage_jours": lien.decalage_jours,
    }
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
    liens = _liens(arbre.projet)
    if not liens:
        return resultat
    cal = None
    if any(lien.decalage_jours for lien in liens):
        dates = [
            d
            for elem in arbre.elements
            for d in (elem.date_debut_prevue, elem.date_fin_prevue)
            if d is not None
        ]
        max_lag = max((abs(lien.decalage_jours) for lien in liens), default=0)
        cal = _calendrier_effectif(dates, decalage_jours=max_lag)
    for lien in liens:
        a, b = arbre.par_id.get(lien.predecesseur_id), arbre.par_id.get(lien.successeur_id)
        if a is None or b is None:
            continue
        ok = respectee(
            a,
            b,
            type_lien=lien.type_lien,
            decalage_jours=lien.decalage_jours,
            calendrier=cal,
        )
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
# Contraintes des prédécesseurs (FS, SS, FF, SF + décalage en jours ouvrés)
# --------------------------------------------------------------------------
def _cible_contrainte_lien(
    predecesseur,
    *,
    a_debut: date | None,
    a_fin: date | None,
    type_lien: str,
    decalage_jours: int,
    calendrier: Calendrier,
) -> tuple[str, date] | None:
    """Calcule la date borne imposée par `predecesseur` selon `type_lien` et `decalage_jours`.

    Rend `("debut", date_min)` pour `FS`/`SS`, `("fin", date_min)` pour `FF`/`SF`, ou `None`
    si la date de référence du prédécesseur manque.
    """
    code = (type_lien or TypeDependance.FS).upper()
    decalage = int(decalage_jours or 0)

    if code == TypeDependance.FS:
        if a_fin is None:
            return None
        cible_fs = date_cible_fs(
            a_fin, decalage, calendrier, est_jalon=_est_jalon(predecesseur)
        )
        return "debut", cible_fs
    if code == TypeDependance.SS:
        if a_debut is None:
            return None
        return "debut", decaler_jours_ouvres(a_debut, decalage, calendrier)
    if code == TypeDependance.FF:
        if a_fin is None:
            return None
        return "fin", decaler_jours_ouvres(a_fin, decalage, calendrier)
    if code == TypeDependance.SF:
        if a_debut is None:
            return None
        return "fin", decaler_jours_ouvres(a_debut, decalage, calendrier)
    return None


def date_debut_au_plus_tot(
    feuille,
    fins: dict | None = None,
    *,
    debuts: dict | None = None,
    calendrier: Calendrier | None = None,
):
    """Date de début au plus tôt imposée par les prédécesseurs (`FS` et `SS`) actifs et datés.

    `fins` et `debuts` permettent de substituer certaines dates en simulation.
    Rend `(date_au_plus_tot, predecesseur_bloquant)` ou `(None, None)`.
    """
    fins = fins or {}
    debuts = debuts or {}
    liens = list(Dependance.objects.filter(successeur=feuille).select_related("predecesseur"))
    if not liens:
        return None, None
    dates = [
        d
        for lien in liens
        for d in (
            debuts.get(lien.predecesseur_id, lien.predecesseur.date_debut_prevue),
            fins.get(lien.predecesseur_id, lien.predecesseur.date_fin_prevue),
        )
        if d is not None
    ]
    max_lag = max((abs(lien.decalage_jours) for lien in liens), default=0)
    cal = _calendrier_effectif(dates, calendrier, max_lag)

    plus_tard: date | None = None
    bloquant = None
    for lien in liens:
        predecesseur = lien.predecesseur
        if not predecesseur.est_actif:
            continue
        cible = _cible_contrainte_lien(
            predecesseur,
            a_debut=debuts.get(predecesseur.pk, predecesseur.date_debut_prevue),
            a_fin=fins.get(predecesseur.pk, predecesseur.date_fin_prevue),
            type_lien=lien.type_lien,
            decalage_jours=lien.decalage_jours,
            calendrier=cal,
        )
        if cible is None or cible[0] != "debut":
            continue
        date_min = cible[1]
        if plus_tard is None or date_min > plus_tard:
            plus_tard, bloquant = date_min, predecesseur
    if plus_tard is None:
        return None, None
    return plus_tard, bloquant


def _erreur_dependance_non_respectee(
    predecesseur: Element,
    successeur: Element,
    *,
    type_lien: str,
    decalage_jours: int,
    date_successeur: date,
    date_min: date,
    est_contrainte_fin: bool,
) -> DependanceNonRespectee:
    lien_txt = _libelle_lien(type_lien, decalage_jours)
    details: dict = {
        "predecesseur": {
            "id": str(predecesseur.pk),
            "libelle": predecesseur.libelle,
            "date_debut_prevue": predecesseur.date_debut_prevue,
            "date_fin_prevue": predecesseur.date_fin_prevue,
        },
        "type_lien": type_lien,
        "decalage_jours": decalage_jours,
    }
    if est_contrainte_fin:
        details["date_fin_au_plus_tot"] = date_min
        ref_date = (
            predecesseur.date_fin_prevue
            if type_lien == TypeDependance.FF
            else predecesseur.date_debut_prevue
        )
        message = _(
            "« %(succ)s » ne peut pas finir le %(date_succ)s : la dépendance %(lien)s avec "
            "« %(pred)s » (%(date_pred)s) impose une fin au plus tôt le %(date_min)s."
        ) % {
            "succ": successeur.libelle,
            "date_succ": formater_date(date_successeur),
            "lien": lien_txt,
            "pred": predecesseur.libelle,
            "date_pred": formater_date(ref_date),
            "date_min": formater_date(date_min),
        }
    else:
        details["date_debut_au_plus_tot"] = date_min
        ref_date = (
            predecesseur.date_fin_prevue
            if type_lien == TypeDependance.FS
            else predecesseur.date_debut_prevue
        )
        message = _(
            "« %(succ)s » ne peut pas commencer le %(date_succ)s : la dépendance %(lien)s avec "
            "« %(pred)s » (%(date_pred)s) impose un début au plus tôt le %(date_min)s."
        ) % {
            "succ": successeur.libelle,
            "date_succ": formater_date(date_successeur),
            "lien": lien_txt,
            "pred": predecesseur.libelle,
            "date_pred": formater_date(ref_date),
            "date_min": formater_date(date_min),
        }
    return DependanceNonRespectee(str(message), details=details)


def verifier_predecesseurs(
    feuille,
    debut: date | None,
    fin: date | None = _NON_FOURNI,
) -> None:
    """Refuse des dates qui violent l'un des prédécesseurs (`FS`, `SS`, `FF`, `SF` + décalage)."""
    fin_cible = feuille.date_fin_prevue if fin is _NON_FOURNI else fin
    if debut is None and fin_cible is None:
        return
    liens = list(Dependance.objects.filter(successeur=feuille).select_related("predecesseur"))
    if not liens:
        return
    dates = [debut, fin_cible] + [
        d
        for lien in liens
        for d in (lien.predecesseur.date_debut_prevue, lien.predecesseur.date_fin_prevue)
    ]
    max_lag = max((abs(lien.decalage_jours) for lien in liens), default=0)
    cal = _calendrier_effectif(dates, decalage_jours=max_lag)

    pire_debut = None
    pire_fin = None
    for lien in liens:
        pred = lien.predecesseur
        if not pred.est_actif:
            continue
        est_ok = _lien_respecte_dates(
            pred_est_jalon=_est_jalon(pred),
            a_debut=pred.date_debut_prevue,
            a_fin=pred.date_fin_prevue,
            b_debut=debut,
            b_fin=fin_cible,
            type_lien=lien.type_lien,
            decalage_jours=lien.decalage_jours,
            calendrier=cal,
        )
        if est_ok is not False:
            continue
        cible = _cible_contrainte_lien(
            pred,
            a_debut=pred.date_debut_prevue,
            a_fin=pred.date_fin_prevue,
            type_lien=lien.type_lien,
            decalage_jours=lien.decalage_jours,
            calendrier=cal,
        )
        if cible is None:
            continue
        nature, date_min = cible
        if nature == "debut":
            if pire_debut is None or date_min > pire_debut[0]:
                pire_debut = (date_min, pred, lien)
        else:
            if pire_fin is None or date_min > pire_fin[0]:
                pire_fin = (date_min, pred, lien)

    if pire_debut is not None:
        date_min, pred, lien = pire_debut
        raise _erreur_dependance_non_respectee(
            pred,
            feuille,
            type_lien=lien.type_lien,
            decalage_jours=lien.decalage_jours,
            date_successeur=debut,
            date_min=date_min,
            est_contrainte_fin=False,
        )
    if pire_fin is not None:
        date_min, pred, lien = pire_fin
        raise _erreur_dependance_non_respectee(
            pred,
            feuille,
            type_lien=lien.type_lien,
            decalage_jours=lien.decalage_jours,
            date_successeur=fin_cible,
            date_min=date_min,
            est_contrainte_fin=True,
        )


# --------------------------------------------------------------------------
# Reprogrammer A : décaler ses successeurs (durée ouvrée conservée)
# --------------------------------------------------------------------------
@dataclass
class Decalage:
    """Un successeur impacté, et les dates qu'il prendrait s'il est décalé."""

    cible: Element
    debut_avant: date | None
    fin_avant: date | None
    debut_apres: date | None
    fin_apres: date | None
    apres: Element  # le prédécesseur qui impose la nouvelle date

    def en_dict(self) -> dict:
        if self.debut_apres and self.debut_avant:
            jours = (self.debut_apres - self.debut_avant).days
        elif self.fin_apres and self.fin_avant:
            jours = (self.fin_apres - self.fin_avant).days
        else:
            jours = 0
        return {
            "id": str(self.cible.pk),
            "libelle": self.cible.libelle,
            "date_debut_avant": self.debut_avant,
            "date_fin_avant": self.fin_avant,
            "date_debut_apres": self.debut_apres,
            "date_fin_apres": self.fin_apres,
            "jours": jours,
            "apres": {"id": str(self.apres.pk), "libelle": self.apres.libelle},
            "decaler_aussi": True,
        }


def decalages_necessaires(
    element,
    nouvelle_fin: date | None,
    nouveau_debut: date | None = None,
) -> list[Decalage]:
    """Les successeurs (de proche en proche) violés si `element` passe aux dates
    `(nouveau_debut, nouvelle_fin)`, avec leurs nouvelles dates **à durée ouvrée conservée**."""
    debut_effectif = nouveau_debut if nouveau_debut is not None else element.date_debut_prevue
    if nouvelle_fin is None and debut_effectif is None:
        return []
    liens = _liens(element.projet)
    if not liens:
        return []
    ids_lies = {i for lien in liens for i in (lien.predecesseur_id, lien.successeur_id)}
    if element.pk not in ids_lies:
        return []

    liens_sortants: dict = defaultdict(list)
    liens_entrants: dict = defaultdict(list)
    for lien in liens:
        liens_sortants[lien.predecesseur_id].append(lien)
        liens_entrants[lien.successeur_id].append(lien)

    cases = {e.pk: e for e in Element.objects.filter(pk__in=ids_lies)}
    debuts = {pk: c.date_debut_prevue for pk, c in cases.items()}
    fins = {pk: c.date_fin_prevue for pk, c in cases.items()}
    if debut_effectif is not None:
        debuts[element.pk] = debut_effectif
    if nouvelle_fin is not None:
        fins[element.pk] = nouvelle_fin

    toutes_dates = [
        d for pk in cases for d in (debuts[pk], fins[pk]) if d is not None
    ]
    max_lag = max((abs(lien.decalage_jours) for lien in liens), default=0)
    cal = _calendrier_effectif(toutes_dates, decalage_jours=max_lag)

    durees_ouvrees: dict = {}
    for pk, c in cases.items():
        if c.date_debut_prevue and c.date_fin_prevue:
            durees_ouvrees[pk] = (
                0
                if _est_jalon(c)
                else compter_duree_ouvree(c.date_debut_prevue, c.date_fin_prevue, cal)
            )
        else:
            durees_ouvrees[pk] = None

    decalages: dict = {}
    a_voir = [element.pk]
    visites = 0
    limite_visites = len(cases) * (len(liens) + 1) + 50

    while a_voir and visites < limite_visites:
        courant = a_voir.pop(0)
        visites += 1
        for lien_sortant in liens_sortants.get(courant, []):
            suivant = lien_sortant.successeur_id
            case = cases.get(suivant)
            if case is None or not case.est_actif:
                continue
            if debuts[suivant] is None and fins[suivant] is None:
                continue

            min_debut: date | None = None
            impose_debut_par = None
            min_fin: date | None = None
            impose_fin_par = None

            for lien_in in liens_entrants[suivant]:
                pred = cases.get(lien_in.predecesseur_id)
                if pred is None or not pred.est_actif:
                    continue
                est_ok = _lien_respecte_dates(
                    pred_est_jalon=_est_jalon(pred),
                    a_debut=debuts[pred.pk],
                    a_fin=fins[pred.pk],
                    b_debut=debuts[suivant],
                    b_fin=fins[suivant],
                    type_lien=lien_in.type_lien,
                    decalage_jours=lien_in.decalage_jours,
                    calendrier=cal,
                )
                if est_ok is not False:
                    continue
                cible = _cible_contrainte_lien(
                    pred,
                    a_debut=debuts[pred.pk],
                    a_fin=fins[pred.pk],
                    type_lien=lien_in.type_lien,
                    decalage_jours=lien_in.decalage_jours,
                    calendrier=cal,
                )
                if cible is None:
                    continue
                nature, date_min = cible
                if nature == "debut":
                    if min_debut is None or date_min > min_debut:
                        min_debut, impose_debut_par = date_min, pred
                else:
                    if min_fin is None or date_min > min_fin:
                        min_fin, impose_fin_par = date_min, pred

            if min_debut is None and min_fin is None:
                continue

            new_debut = debuts[suivant]
            new_fin = fins[suivant]
            duree_b = durees_ouvrees[suivant]
            est_jalon_b = _est_jalon(case)
            imposee_par = impose_debut_par or impose_fin_par

            if min_debut is not None:
                new_debut = min_debut
                if duree_b is not None:
                    new_fin = (
                        new_debut
                        if est_jalon_b
                        else fin_apres_duree_ouvree(new_debut, duree_b, cal)
                    )

            if min_fin is not None and (new_fin is None or new_fin < min_fin):
                new_fin = min_fin
                imposee_par = impose_fin_par
                if new_debut is not None and duree_b is not None:
                    debut_pour_fin = (
                        new_fin if est_jalon_b else _debut_avant_duree_ouvree(new_fin, duree_b, cal)
                    )
                    plancher = min_debut if min_debut is not None else debuts[suivant]
                    new_debut = max(plancher, debut_pour_fin) if plancher else debut_pour_fin
                if new_debut is not None and new_debut > new_fin:
                    new_fin = new_debut

            if (new_debut, new_fin) == (debuts[suivant], fins[suivant]):
                continue

            if suivant not in decalages:
                decalages[suivant] = Decalage(
                    cible=case,
                    debut_avant=case.date_debut_prevue,
                    fin_avant=case.date_fin_prevue,
                    debut_apres=new_debut,
                    fin_apres=new_fin,
                    apres=imposee_par,
                )
            else:
                decalages[suivant].debut_apres = new_debut
                decalages[suivant].fin_apres = new_fin
                decalages[suivant].apres = imposee_par

            debuts[suivant], fins[suivant] = new_debut, new_fin
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
    nouveau_debut: date | None = None,
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

    decalages = decalages_necessaires(element, nouvelle_fin, nouveau_debut=nouveau_debut)
    if not decalages:
        return []
    confirmes = {str(i) for i in (decaler_successeurs or [])}
    oublies = [d for d in decalages if str(d.cible.pk) not in confirmes]
    if decaler_successeurs is None or oublies:
        cites = oublies or decalages
        noms = ", ".join(f"« {d.cible.libelle} »" for d in cites)
        if len(cites) == 1:
            message = _(
                "Ce report impacterait %(noms)s au regard de ses dépendances : confirmez son "
                "décalage, ou choisissez d'autres dates."
            ) % {"noms": noms}
        else:
            message = _(
                "Ce report impacterait %(noms)s au regard de leurs dépendances : confirmez leur "
                "décalage, ou choisissez d'autres dates."
            ) % {"noms": noms}
        raise SuccesseursADecaler(
            str(message),
            details={
                "successeurs": [d.en_dict() for d in decalages],
                "non_confirmes": [str(d.cible.pk) for d in oublies or decalages],
            },
        )
    if motif is None:
        raise ValidationError(
            {"motif_id": _("Décaler les tâches qui suivent est un report : le motif est requis.")}
        )
    resultats = []
    for decalage in decalages:
        cible = Element.objects.get(pk=decalage.cible.pk)
        if not autorise("projets.planifier", cible):
            raise PermissionDenied(
                _(
                    "Décaler « %(libelle)s » exige la permission « projets.planifier » sur "
                    "cette tâche : elle n'est pas dans votre périmètre."
                )
                % {"libelle": cible.libelle}
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
def ajouter_lien(
    predecesseur: Element,
    successeur: Element,
    *,
    type_lien: str = TypeDependance.FS,
    decalage_jours: int = 0,
    auteur=None,
) -> Dependance:
    """Relie deux feuilles actives du même projet selon `type_lien` (`FS`, `SS`, `FF`, `SF`)
    et un décalage signé `decalage_jours` en jours ouvrés."""
    code_type = _normaliser_type_lien(type_lien)
    decalage = int(decalage_jours or 0)

    if predecesseur.projet_id != successeur.projet_id:
        raise ErreurMetier(_("Deux tâches de projets différents ne se lient pas."))
    if predecesseur.pk == successeur.pk:
        raise ErreurMetier(_("Une tâche ne se suit pas elle-même."))
    arbre = charger_arbre(predecesseur.projet)
    a, b = arbre.par_id[predecesseur.pk], arbre.par_id[successeur.pk]
    for case in (a, b):
        if not case.est_actif or any(not x.est_actif for x in arbre.ancetres(case)):
            raise ErreurMetier(
                _("« %(libelle)s » est désactivée : elle ne se lie plus.")
                % {"libelle": case.libelle}
            )
        if not arbre.est_feuille(case):
            raise ErreurMetier(
                _(
                    "« %(libelle)s » a des sous-tâches : les dépendances relient des tâches du "
                    "bas (des feuilles)."
                )
                % {"libelle": case.libelle}
            )
    liens = _liens(arbre.projet)
    if any(x.predecesseur_id == a.pk and x.successeur_id == b.pk for x in liens):
        raise ErreurConflit(
            _("« %(succ)s » suit déjà « %(pred)s ».") % {"succ": b.libelle, "pred": a.libelle}
        )
    successeurs, _predecesseurs = _graphe(liens)
    boucle = _chemin_vers(b.pk, a.pk, successeurs)
    if boucle is not None:
        noms = " → ".join(f"« {arbre.par_id[i].libelle} »" for i in [*boucle, b.pk])
        raise BoucleDependances(
            _("Ce lien fermerait une boucle : %(boucle)s.") % {"boucle": noms},
            details={"boucle": [str(i) for i in [*boucle, b.pk]]},
        )

    cal = _calendrier_effectif(
        [a.date_debut_prevue, a.date_fin_prevue, b.date_debut_prevue, b.date_fin_prevue],
        decalage_jours=decalage,
    )
    if (
        respectee(a, b, type_lien=code_type, decalage_jours=decalage, calendrier=cal)
        is False
    ):
        cible = _cible_contrainte_lien(
            a,
            a_debut=a.date_debut_prevue,
            a_fin=a.date_fin_prevue,
            type_lien=code_type,
            decalage_jours=decalage,
            calendrier=cal,
        )
        est_fin = cible is not None and cible[0] == "fin"
        date_min = cible[1] if cible is not None else a.date_fin_prevue
        date_succ = b.date_fin_prevue if est_fin else b.date_debut_prevue
        raise _erreur_dependance_non_respectee(
            a,
            b,
            type_lien=code_type,
            decalage_jours=decalage,
            date_successeur=date_succ,
            date_min=date_min,
            est_contrainte_fin=est_fin,
        )

    try:
        lien = Dependance.objects.create(
            projet=a.projet,
            predecesseur=a,
            successeur=b,
            type_lien=code_type,
            decalage_jours=decalage,
            cree_par=auteur,
        )
    except IntegrityError:
        raise ErreurConflit(
            _("« %(succ)s » suit déjà « %(pred)s ».") % {"succ": b.libelle, "pred": a.libelle}
        ) from None
    _tracer_audit(
        b,
        auteur,
        "LIEN_AJOUT",
        apres={
            "predecesseur": str(a.pk),
            "lien": str(lien.pk),
            "type_lien": code_type,
            "decalage_jours": decalage,
        },
    )
    _tracer_audit(
        a,
        auteur,
        "LIEN_AJOUT",
        apres={
            "successeur": str(b.pk),
            "lien": str(lien.pk),
            "type_lien": code_type,
            "decalage_jours": decalage,
        },
    )
    return lien


@transaction.atomic
def retirer_lien(lien: Dependance, *, auteur=None) -> None:
    lien.delete(utilisateur=auteur)
    _tracer_audit(
        lien.successeur,
        auteur,
        "LIEN_RETRAIT",
        avant={
            "predecesseur": str(lien.predecesseur_id),
            "lien": str(lien.pk),
            "type_lien": lien.type_lien,
            "decalage_jours": lien.decalage_jours,
        },
    )
    _tracer_audit(
        lien.predecesseur,
        auteur,
        "LIEN_RETRAIT",
        avant={
            "successeur": str(lien.successeur_id),
            "lien": str(lien.pk),
            "type_lien": lien.type_lien,
            "decalage_jours": lien.decalage_jours,
        },
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
                        "type_lien": x.type_lien,
                        "decalage_jours": x.decalage_jours,
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
    un parent) et leurs `type_lien` / `decalage_jours` sont conservés.
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
                    type_lien=lien.type_lien,
                    decalage_jours=lien.decalage_jours,
                    cree_par=auteur,
                )
            )
    successeurs = {x.successeur for x in liens if x.predecesseur_id == ancienne_feuille.pk}
    for feuille in [*feuilles, *successeurs]:
        verifier_predecesseurs(feuille, feuille.date_debut_prevue, feuille.date_fin_prevue)
    _tracer_audit(
        ancienne_feuille,
        auteur,
        "LIENS_HERITES_DETAIL",
        avant={"liens": [str(x.pk) for x in liens]},
        apres={
            "feuilles": [str(f.pk) for f in feuilles],
            "liens": [
                {
                    "predecesseur": str(x.predecesseur_id),
                    "successeur": str(x.successeur_id),
                    "type_lien": x.type_lien,
                    "decalage_jours": x.decalage_jours,
                }
                for x in crees
            ],
        },
    )
    return len(crees)
