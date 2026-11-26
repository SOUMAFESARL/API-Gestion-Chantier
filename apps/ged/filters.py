"""Filtres django-filter et recherche rapide (< 1 s) du module GED (tâche 3.11)."""

from __future__ import annotations

import django_filters
from django.db.models import Exists, OuterRef, Q

from apps.core.enums import CategorieDocument, TypeSourceLiaison
from apps.ged.models import Document, LiaisonDocument, VersionDocument

__all__ = ["DocumentFilter"]


class DocumentFilter(django_filters.FilterSet):
    """Filtres combinables de `GET /api/v1/ged/documents/`.

    Utilise `Exists(Subquery)` sur `LiaisonDocument` et `VersionDocument` afin de ne jamais
    provoquer de doublons SQL lors des recherches sur documents multi-versions.
    """

    projet = django_filters.UUIDFilter(field_name="projet_id")
    categorie = django_filters.CharFilter(method="filtrer_categorie")
    origine = django_filters.CharFilter(method="filtrer_origine")
    est_reference = django_filters.BooleanFilter(field_name="est_reference")
    q = django_filters.CharFilter(method="filtrer_recherche")
    date_debut = django_filters.DateFilter(field_name="cree_le", lookup_expr="date__gte")
    date_fin = django_filters.DateFilter(field_name="cree_le", lookup_expr="date__lte")

    class Meta:
        model = Document
        fields = [
            "projet",
            "categorie",
            "origine",
            "est_reference",
            "q",
            "date_debut",
            "date_fin",
        ]

    def filtrer_categorie(self, queryset, name, value):
        code = (value or "").strip().upper()
        if not code:
            return queryset
        if code not in CategorieDocument.values:
            return queryset.none()
        return queryset.filter(categorie=code)

    def filtrer_origine(self, queryset, name, value):
        code = (value or "").strip().upper()
        if not code:
            return queryset
        if code == "MANUEL":
            return queryset.filter(est_automatique=False)
        if code in TypeSourceLiaison.values:
            sous_req = LiaisonDocument.objects.filter(
                document_id=OuterRef("pk"),
                type_source=code,
                supprime_le__isnull=True,
            )
            return queryset.filter(est_automatique=True).filter(Exists(sous_req))
        return queryset.none()

    def filtrer_recherche(self, queryset, name, value):
        terme = (value or "").strip()
        if not terme:
            return queryset

        version_correspondante = VersionDocument.objects.filter(
            document_id=OuterRef("pk"),
            supprime_le__isnull=True,
        ).filter(
            Q(nom_fichier__icontains=terme)
            | Q(fichier__icontains=terme)
            | Q(commentaire__icontains=terme)
        )

        return queryset.filter(
            Q(nom__icontains=terme)
            | Q(description__icontains=terme)
            | Q(projet__nom__icontains=terme)
            | Q(projet__reference__icontains=terme)
            | Exists(version_correspondante)
        )
