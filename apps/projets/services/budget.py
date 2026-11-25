"""Le budget d'un projet, lu sur son arbre : ce qui est chiffré, ce qui est réalisé.

Avant ce module, la carte Budget de la fiche et le tableau de bord lisaient un « budget consommé »
que **rien ne calculait** : il valait 0 partout, le reste à engager était le budget entier, le
ratio restait à 0 % et aucun dépassement ne pouvait se voir.

Le projet n'a pas de module financier : on ne sait pas ce qui a été **dépensé**. Ce qu'on sait,
c'est ce qui a été **réalisé**, lu sur le **poids effectif** des racines actives de l'arbre
(`calculer_arbre(arbre)` : somme des feuilles chiffrées ou `enveloppe` du parent, sans double
comptage) :

    montant chiffré  = Σ poids effectif des racines actives
    réalisé valorisé = Σ (poids effectif de la racine x son avancement physique / 100)

Le jour où un module financier existera, le dépensé réel remplacera cette valeur sans changer les
écrans. D'ici là, on l'appelle « réalisé », pas « consommé » : un réalisé n'est pas de l'argent
sorti. Tous les montants sont en centimes de FCFA, comme partout.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from apps.projets.services.sante_calculs import calculer_arbre

__all__ = ["montant_chiffre", "realise_valorise"]


def montant_chiffre(arbre) -> int:
    """Somme des poids effectifs des racines actives (feuilles chiffrées ou enveloppes),
    sans double comptage."""
    resultats = calculer_arbre(arbre)
    total = sum(
        (
            resultats[racine.pk].poids
            for racine in arbre.racines()
            if racine.est_actif and resultats.get(racine.pk) and resultats[racine.pk].poids
        ),
        Decimal(0),
    )
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def realise_valorise(arbre) -> int:
    """Valeur de ce qui est réalisé : Σ poids x avancement / 100 des racines actives,
    sans double comptage.

    Inclut les périmètres chiffrés par enveloppe parente ; une feuille clôturée vaut son montant
    entier et un dépassement de quantité reste plafonné à 100 %.
    """
    resultats = calculer_arbre(arbre)
    total = Decimal(0)
    for racine in arbre.racines():
        if not racine.est_actif:
            continue
        resultat = resultats.get(racine.pk)
        if resultat and resultat.poids and resultat.physique is not None:
            total += resultat.poids * Decimal(str(resultat.physique)) / Decimal(100)
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
