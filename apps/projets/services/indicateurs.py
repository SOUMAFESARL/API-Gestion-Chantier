"""Indicateurs de présentation sans modification de l'avancement stocké."""

from decimal import Decimal

from apps.core.enums import StatutProjet


def avancement_restant(projet):
    """100 % moins le physique du projet, calculé sur l'arbre (décisions v1.2, §9).

    Avancement indisponible (aucun montant connu) : on retombe sur l'avancement stocké.
    """
    from apps.projets.services.sante_calculs import resultat_projet

    if projet.statut == StatutProjet.TERMINE:
        return 0.0
    resultat = resultat_projet(projet)
    realise = (
        Decimal(str(resultat.physique))
        if resultat.physique is not None
        else Decimal(projet.avancement_reel or 0)
    )
    return float(round(max(Decimal(0), min(Decimal(100), 100 - realise)), 2))
