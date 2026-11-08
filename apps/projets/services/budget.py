"""Le budget d'un projet, lu sur son arbre : ce qui est chiffré, ce qui est réalisé.

Avant ce module, la carte Budget de la fiche et le tableau de bord lisaient un « budget consommé »
que **rien ne calculait** : il valait 0 partout, le reste à engager était le budget entier, le
ratio restait à 0 % et aucun dépassement ne pouvait se voir.

Le projet n'a pas de module financier : on ne sait pas ce qui a été **dépensé**. Ce qu'on sait,
c'est ce qui a été **réalisé** — chaque feuille a un montant et un avancement — et sa valeur :

    réalisé valorisé = Σ (montant de la feuille x son avancement physique)

Le jour où un module financier existera, le dépensé réel remplacera cette valeur sans changer les
écrans. D'ici là, on l'appelle « réalisé », pas « consommé » : un réalisé n'est pas de l'argent
sorti. Tous les montants sont en centimes, comme partout.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from apps.projets.services.sante_calculs import calculer_avancement_physique_feuille

__all__ = ["montant_chiffre", "realise_valorise"]


def _montant(feuille) -> int:
    montant = getattr(feuille, "montant", None)
    return int(montant) if montant and montant > 0 else 0


def montant_chiffre(arbre) -> int:
    """La somme des montants des feuilles actives : ce que le découpage chiffre au total."""
    return sum(_montant(feuille) for feuille in arbre.feuilles())


def realise_valorise(arbre) -> int:
    """La valeur de ce qui est réalisé : Σ montant x avancement des feuilles actives.

    Une feuille clôturée vaut son montant entier ; un dépassement de quantité ne la fait pas
    valoir plus (l'avancement est plafonné à 100 %, le dépassement s'affiche ailleurs).
    """
    total = Decimal(0)
    for feuille in arbre.feuilles():
        montant = _montant(feuille)
        if montant:
            avancement = Decimal(str(calculer_avancement_physique_feuille(feuille)))
            total += Decimal(montant) * avancement / 100
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
