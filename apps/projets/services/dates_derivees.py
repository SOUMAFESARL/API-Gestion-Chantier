"""Les dates d'un parent, déduites de ses enfants (décisions v1.2, §11).

Les faits sont sur les feuilles ; un parent qui n'a pas d'engagement propre les **lit** :

- début prévu = le début le plus tôt de ses enfants datés, fin prévue = la fin la plus tard ;
- baseline = l'enveloppe des baselines de ses enfants. Elle ne dépend donc pas de l'ordre dans
  lequel on date les enfants, et elle ne bouge que si un enfant entre ou sort du parent : une
  reprogrammation déplace les dates prévues, jamais la baseline (§11bis).

Un parent est **calculé** tant que personne n'a posé ses dates à la main (`dates_calculees`, ou
aucune date). Dès qu'on les pose, elles sont un engagement : elles bornent les enfants, et le
parent ne se recalcule plus.
"""

from __future__ import annotations

from apps.projets.models import Element
from apps.projets.selectors.arbre import charger_arbre

__all__ = ["est_calcule", "recalculer_dates_derivees"]


def est_calcule(element) -> bool:
    """Vrai si les dates de cette case viennent (ou viendront) de ses enfants.

    Un parent sans aucune date n'a rien promis : il prend celles de ses enfants. Le projet, lui,
    n'est pas une case : ses dates sont toujours une saisie.
    """
    if not isinstance(element, Element):
        return False
    if element.dates_calculees:
        return True
    return element.date_debut_prevue is None and element.date_fin_prevue is None


def _extremes(valeurs, choisir):
    valeurs = [v for v in valeurs if v is not None]
    return choisir(valeurs) if valeurs else None


def recalculer_dates_derivees(projet) -> int:
    """Recale, des feuilles vers les racines, les parents dont les dates sont calculées.

    Rend le nombre de cases modifiées. Sans enfant daté, un parent garde ce qu'il a.
    """
    arbre = charger_arbre(projet, actifs_seulement=True)
    a_jour: list[Element] = []

    def visiter(element) -> None:
        enfants = arbre.enfants_actifs(element)
        if not enfants:
            return
        for enfant in enfants:
            visiter(enfant)
        if not est_calcule(element):
            return
        debut = _extremes((e.date_debut_prevue for e in enfants), min)
        fin = _extremes((e.date_fin_prevue for e in enfants), max)
        if debut is None and fin is None:
            return
        nouveau = {
            "date_debut_prevue": debut,
            "date_fin_prevue": fin,
            "date_debut_baseline": _extremes((e.date_debut_baseline for e in enfants), min),
            "date_fin_baseline": _extremes((e.date_fin_baseline for e in enfants), max),
            "dates_calculees": True,
        }
        if any(getattr(element, champ) != valeur for champ, valeur in nouveau.items()):
            for champ, valeur in nouveau.items():
                setattr(element, champ, valeur)
            a_jour.append(element)

    for racine in arbre.racines():
        if racine.est_actif:
            visiter(racine)

    if a_jour:
        # `bulk_update` plutôt que `save()` : `save()` poserait la baseline v0 sur une première
        # valeur, avant que tous les enfants soient datés.
        Element.objects.bulk_update(
            a_jour,
            [
                "date_debut_prevue",
                "date_fin_prevue",
                "date_debut_baseline",
                "date_fin_baseline",
                "dates_calculees",
            ],
        )
    return len(a_jour)
