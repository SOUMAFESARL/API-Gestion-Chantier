"""Statistiques calculées sur les cases actives de l'arbre, sans dépenses fictives."""

from decimal import Decimal

from django.utils import timezone

from apps.projets.services.sante_calculs import (
    calculer_arbre,
    calculer_avancement_physique_feuille,
    resultat_projet,
)


def pourcentage_realise(feuille):
    """Le pourcentage de réalisation d'une feuille, en Decimal."""
    return Decimal(str(calculer_avancement_physique_feuille(feuille)))


def statistiques_arbre(arbre):
    """Statistiques consolidées de l'arbre d'un projet.

    Même moteur que l'indice de santé (F3 généralisée) : moyenne pondérée par le montant.
    `avancement_pondere` vaut None quand aucun montant n'est connu (« indisponible »).
    """
    resultats = calculer_arbre(arbre)
    resultat = resultat_projet(arbre.projet, arbre, resultats)
    feuilles = arbre.feuilles()
    aujourd_hui = timezone.localdate()
    return {
        "cases_count": sum(1 for e in arbre.elements if e.est_actif),
        "feuilles_count": len(feuilles),
        "avancement_pondere": resultat.physique,
        "avancement_partiel": resultat.partiel,
        "ponderation": "MONTANT",
        "feuilles_en_retard": sum(
            1
            for f in feuilles
            if f.date_fin_prevue
            and f.date_fin_prevue < aujourd_hui
            and not f.cloture
            and calculer_avancement_physique_feuille(f) < 100.0
        ),
    }
