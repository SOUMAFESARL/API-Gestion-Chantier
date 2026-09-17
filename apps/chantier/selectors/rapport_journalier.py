"""Selectors pour l'application chantier — lecture des rapports journaliers.

Architecture selectors/services : toutes les requêtes de lecture complexes
et optimisées sont centralisées ici.
"""

from uuid import UUID

from django.db.models import QuerySet

from apps.chantier.models import RapportJournalier
from apps.core.enums import StatutRapport

__all__ = [
    "rapport_existe",
    "rapport_par_id",
    "rapports_en_attente_validation",
    "rapports_liste",
]


def rapports_liste(
    *,
    projet_id: UUID | str | None = None,
    lot_id: UUID | str | None = None,
    statut: str | None = None,
    auteur_id: UUID | str | None = None,
    date_debut=None,
    date_fin=None,
    meteo: str | None = None,
) -> QuerySet[RapportJournalier]:
    """Retourne la liste filtrée des rapports journaliers avec relations préchargées."""
    qs = RapportJournalier.objects.select_related(
        "projet",
        "lot",
        "auteur",
        "valide_par",
    ).all()

    if projet_id:
        qs = qs.filter(projet_id=projet_id)
    if lot_id:
        qs = qs.filter(lot_id=lot_id)
    if statut:
        qs = qs.filter(statut=statut)
    if auteur_id:
        qs = qs.filter(auteur_id=auteur_id)
    if date_debut:
        qs = qs.filter(date_rapport__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_rapport__lte=date_fin)
    if meteo:
        qs = qs.filter(meteo=meteo)

    return qs.order_by("-date_rapport", "-cree_le")


def rapport_par_id(rapport_id: UUID | str) -> RapportJournalier | None:
    """Retourne le rapport journalier correspondant à l'identifiant, ou None."""
    try:
        return (
            RapportJournalier.objects.select_related(
                "projet",
                "lot",
                "auteur",
                "valide_par",
            )
            .filter(id=rapport_id)
            .first()
        )
    except (ValueError, TypeError):
        return None


def rapport_existe(
    *,
    projet_id: UUID | str,
    lot_id: UUID | str | None = None,
    date_rapport,
    exclure_id: UUID | str | None = None,
) -> bool:
    """Vérifie si un rapport existe déjà pour la même date sur le lot ou le projet."""
    qs = RapportJournalier.objects.filter(date_rapport=date_rapport)

    if exclure_id:
        qs = qs.exclude(id=exclure_id)

    if lot_id:
        return qs.filter(lot_id=lot_id).exists()

    return qs.filter(projet_id=projet_id, lot__isnull=True).exists()


def rapports_en_attente_validation(
    projet_id: UUID | str | None = None,
) -> QuerySet[RapportJournalier]:
    """Retourne la file d'attente des rapports soumis en attente de revue par le CT."""
    return rapports_liste(projet_id=projet_id, statut=StatutRapport.SOUMIS)
