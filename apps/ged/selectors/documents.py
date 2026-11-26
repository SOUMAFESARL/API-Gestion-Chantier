"""Selectors de lecture optimisés pour les documents GED (zéro N+1)."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Prefetch, Q, QuerySet

from apps.core.enums import TypeSourceLiaison
from apps.core.permissions import filtrer_queryset_par_affectations
from apps.ged.models import Document, LiaisonDocument, VersionDocument
from apps.ged.permissions import categories_visibles_utilisateur

__all__ = [
    "extraire_liaison_principale",
    "extraire_version_active",
    "origine_document",
    "queryset_documents_base",
    "queryset_documents_visibles",
    "sous_type_source_f1",
]


def queryset_documents_base(*, avec_toutes_versions: bool = False) -> QuerySet[Document]:
    """QuerySet de base préchargé sans N+1 (cloisonné par entreprise D9 via `objects`)."""
    prefetches: list[Prefetch] = [
        Prefetch(
            "liaisons",
            queryset=LiaisonDocument.objects.filter(supprime_le__isnull=True).order_by("cree_le"),
            to_attr="liaisons_actives",
        )
    ]

    if avec_toutes_versions:
        prefetches.append(
            Prefetch(
                "versions",
                queryset=VersionDocument.objects.select_related("auteur")
                .filter(supprime_le__isnull=True)
                .order_by("-numero_version"),
                to_attr="versions_ordonnees",
            )
        )
    else:
        prefetches.append(
            Prefetch(
                "versions",
                queryset=VersionDocument.objects.select_related("auteur")
                .filter(est_active=True, supprime_le__isnull=True)
                .order_by("-numero_version"),
                to_attr="versions_actives",
            )
        )

    return (
        Document.objects.select_related("projet", "createur")
        .annotate(
            nb_versions=Count(
                "versions",
                filter=Q(versions__supprime_le__isnull=True),
                distinct=True,
            )
        )
        .prefetch_related(*prefetches)
        .order_by("-est_reference", "-modifie_le", "-cree_le")
    )


def queryset_documents_visibles(
    user: Any,
    request: Any = None,
    *,
    avec_toutes_versions: bool = False,
) -> QuerySet[Document]:
    """Restreint les documents aux projets affectés et aux catégories `ged.voir_<cat>` du rôle."""
    categories = categories_visibles_utilisateur(user, request=request)
    if not categories:
        return Document.objects.none()

    qs = queryset_documents_base(avec_toutes_versions=avec_toutes_versions)
    qs = filtrer_queryset_par_affectations(qs, user, champ_projet="projet_id", request=request)
    return qs.filter(categorie__in=categories)


def extraire_liaison_principale(document: Document) -> LiaisonDocument | None:
    """Retourne la liaison source principale depuis le préchargement (zéro requête)."""
    if not document.est_automatique:
        return None
    liaisons = getattr(document, "liaisons_actives", None)
    if liaisons is not None:
        return liaisons[0] if liaisons else None
    return document.liaisons.filter(supprime_le__isnull=True).order_by("cree_le").first()


def extraire_version_active(document: Document) -> VersionDocument | None:
    """Retourne la version active depuis le préchargement (zéro requête)."""
    versions_actives = getattr(document, "versions_actives", None)
    if versions_actives is not None:
        if versions_actives:
            return versions_actives[0]
        return document.derniere_version

    versions_ordonnees = getattr(document, "versions_ordonnees", None)
    if versions_ordonnees is not None:
        for version in versions_ordonnees:
            if version.est_active:
                return version
        return versions_ordonnees[0] if versions_ordonnees else None

    return document.derniere_version


def origine_document(document: Document) -> str:
    """Déduit l'origine métier (`MANUEL`, `F1_CONTRAT`, `F2_RAPPORT`, `F9_BRV`)."""
    if not document.est_automatique:
        return "MANUEL"
    liaison = extraire_liaison_principale(document)
    if liaison and liaison.type_source:
        return str(liaison.type_source)
    return TypeSourceLiaison.F1_CONTRAT


def sous_type_source_f1(document: Document, liaison: LiaisonDocument | None) -> str | None:
    """Précise la nature F1 (`CONTRAT`, `ORDRE_SERVICE`, `AVENANT`) sans requête SQL."""
    if liaison is None or liaison.type_source != TypeSourceLiaison.F1_CONTRAT:
        return None
    if str(liaison.objet_id) == str(document.projet_id):
        return "ORDRE_SERVICE"
    nom = (document.nom or "").lower()
    if "avenant" in nom:
        return "AVENANT"
    return "CONTRAT"
