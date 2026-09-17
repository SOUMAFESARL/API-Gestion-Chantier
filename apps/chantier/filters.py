"""Filtres django-filter pour l'application chantier."""

import django_filters

from apps.chantier.models import RapportJournalier
from apps.core.enums import Meteo, StatutRapport

__all__ = ["RapportJournalierFilter"]


class RapportJournalierFilter(django_filters.FilterSet):
    """Filtres applicables sur la liste des rapports journaliers."""

    projet = django_filters.UUIDFilter(field_name="projet_id")
    lot = django_filters.UUIDFilter(field_name="lot_id")
    auteur = django_filters.UUIDFilter(field_name="auteur_id")
    valide_par = django_filters.UUIDFilter(field_name="valide_par_id")
    statut = django_filters.ChoiceFilter(choices=StatutRapport.choices)
    meteo = django_filters.ChoiceFilter(choices=Meteo.choices)
    date_debut = django_filters.DateFilter(field_name="date_rapport", lookup_expr="gte")
    date_fin = django_filters.DateFilter(field_name="date_rapport", lookup_expr="lte")
    date_rapport = django_filters.DateFilter(field_name="date_rapport")

    class Meta:
        model = RapportJournalier
        fields = [
            "projet",
            "lot",
            "auteur",
            "valide_par",
            "statut",
            "meteo",
            "date_debut",
            "date_fin",
            "date_rapport",
        ]
