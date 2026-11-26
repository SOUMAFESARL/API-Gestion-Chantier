"""Vues REST des documents, versions et téléchargements GED (tâches 3.3, 3.6, 3.8, 3.11)."""

from __future__ import annotations

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import a_permission, est_dg
from apps.core.enums import ActionAudit
from apps.ged.filters import DocumentFilter
from apps.ged.models import Document, VersionDocument
from apps.ged.permissions import (
    PermissionDocumentParCategorie,
    PeutTelechargerDocument,
    obtenir_code_permission_categorie,
    verifier_acces_projet_ged,
)
from apps.ged.selectors.documents import (
    extraire_version_active,
    queryset_documents_base,
    queryset_documents_visibles,
)
from apps.ged.serializers.documents import (
    DocumentDepotSerializer,
    DocumentGedDetailSerializer,
    DocumentGedSerializer,
    DocumentModificationSerializer,
    DocumentSuppressionSerializer,
    NouvelleVersionSerializer,
    VersionDocumentSerializer,
)
from apps.ged.services.audit import journaliser_evenement_ged
from apps.ged.services.documents import (
    ajouter_version,
    deposer_document,
    modifier_document,
    supprimer_document,
)
from apps.projets.models import Projet

__all__ = [
    "DocumentDetailView",
    "DocumentListCreateView",
    "DocumentTelechargerView",
    "DocumentVersionTelechargerView",
    "DocumentVersionsView",
    "PaginationGed",
]

TAGS = ["ged"]


class PaginationGed(PageNumberPagination):
    """Pagination conforme au contrat frontend GED (`count`, `next`, `previous`, `results`)."""

    page_size = 200
    page_size_query_param = "taille_page"
    max_page_size = 500


class DocumentListCreateView(APIView):
    """`GET` et `POST /api/v1/ged/documents/` — liste/recherche rapide & dépôt initial (v1)."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAuthenticated, PermissionDocumentParCategorie]

    @extend_schema(
        tags=TAGS,
        summary="Lister et rechercher les documents GED accessibles",
        parameters=[
            OpenApiParameter("projet", OpenApiTypes.UUID, description="UUID du projet"),
            OpenApiParameter(
                "categorie", OpenApiTypes.STR, description="Catégorie BTP (6 valeurs)"
            ),
            OpenApiParameter(
                "origine",
                OpenApiTypes.STR,
                description="MANUEL | F1_CONTRAT | F2_RAPPORT | F9_BRV",
            ),
            OpenApiParameter(
                "est_reference", OpenApiTypes.BOOL, description="Documents épinglés uniquement"
            ),
            OpenApiParameter(
                "q",
                OpenApiTypes.STR,
                description="Recherche plein texte (nom, description, fichier)",
            ),
            OpenApiParameter(
                "date_debut", OpenApiTypes.DATE, description="Date début ISO YYYY-MM-DD"
            ),
            OpenApiParameter("date_fin", OpenApiTypes.DATE, description="Date fin ISO YYYY-MM-DD"),
        ],
        responses={200: DocumentGedSerializer(many=True)},
    )
    def get(self, request):
        qs = queryset_documents_visibles(request.user, request=request)
        filtre = DocumentFilter(request.query_params, queryset=qs, request=request)
        qs_filtre = filtre.qs

        paginator = PaginationGed()
        page = paginator.paginate_queryset(qs_filtre, request, view=self)
        serializer = DocumentGedSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=TAGS,
        summary="Déposer un nouveau document dans le classeur GED (version initiale v1)",
        request={"multipart/form-data": DocumentDepotSerializer},
        responses={
            201: DocumentGedSerializer,
            400: OpenApiResponse(description="Champs invalides ou format de fichier non autorisé."),
            403: OpenApiResponse(description="Droit de dépôt ou affectation projet refusé."),
            413: OpenApiResponse(description="Taille du fichier supérieure à 50 Mo."),
        },
    )
    def post(self, request):
        entree = DocumentDepotSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data

        projet = get_object_or_404(
            Projet.objects.select_related("entreprise"), pk=donnees["projet"]
        )

        # Défense en profondeur : contrôle cumulatif projet + catégorie sur les données validées
        if not verifier_acces_projet_ged(request.user, projet, request=request):
            raise PermissionDenied(_("Vous n'êtes pas affecté à ce projet."))

        if not (request.user.is_superuser or est_dg(request.user)):
            code_perm = obtenir_code_permission_categorie("deposer", donnees["categorie"])
            if not a_permission(request.user, code_perm, request=request):
                raise PermissionDenied(
                    _(
                        f"Vous n'avez pas la permission de déposer des documents "
                        f"dans la catégorie '{donnees['categorie']}'."
                    )
                )

        document, _version = deposer_document(
            projet=projet,
            categorie=donnees["categorie"],
            fichier=donnees["fichier"],
            nom=donnees["nom"],
            createur=request.user,
            est_reference=donnees["est_reference"],
            description=donnees["description"],
            commentaire=donnees["commentaire"],
            request=request,
        )

        document_charge = queryset_documents_base().get(pk=document.pk)
        return Response(
            DocumentGedSerializer(document_charge, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailView(APIView):
    """`GET`, `PATCH`, `DELETE /api/v1/ged/documents/{id}/`."""

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated, PermissionDocumentParCategorie]

    def _charger_document(self, request, pk, *, avec_versions: bool = False) -> Document:
        document = get_object_or_404(
            queryset_documents_base(avec_toutes_versions=avec_versions),
            pk=pk,
        )
        self.check_object_permissions(request, document)
        return document

    @extend_schema(
        tags=TAGS,
        summary="Consulter le détail d'un document GED et ses versions",
        responses={200: DocumentGedDetailSerializer},
    )
    def get(self, request, pk):
        document = self._charger_document(request, pk, avec_versions=True)
        version_active = extraire_version_active(document)
        details = (
            f"Consultation de la fiche ({version_active.numero})"
            if version_active
            else "Consultation de la fiche document"
        )
        journaliser_evenement_ged(
            action=ActionAudit.CONSULTATION,
            document=document,
            utilisateur=request.user,
            details=details,
            request=request,
            extra={"version": version_active.numero} if version_active else None,
        )
        return Response(
            DocumentGedDetailSerializer(document, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=TAGS,
        summary="Épingler en document de référence ou modifier les métadonnées (document manuel)",
        request=DocumentModificationSerializer,
        responses={200: DocumentGedSerializer},
    )
    def patch(self, request, pk):
        document = self._charger_document(request, pk)
        entree = DocumentModificationSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data

        modifier_document(
            document=document,
            utilisateur=request.user,
            est_reference=donnees.get("est_reference"),
            nom=donnees.get("nom"),
            description=donnees.get("description"),
            request=request,
        )

        document_maj = queryset_documents_base().get(pk=document.pk)
        return Response(
            DocumentGedSerializer(document_maj, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=TAGS,
        summary="Supprimer logiquement un document manuel (AD ou CP uniquement)",
        request=DocumentSuppressionSerializer,
        responses={
            204: None,
            403: OpenApiResponse(
                description="Suppression réservée à AD / CP avec droit catégorie."
            ),
            422: OpenApiResponse(description="Document automatique non supprimable."),
        },
    )
    def delete(self, request, pk):
        document = self._charger_document(request, pk)
        motif = ""
        if request.data:
            entree = DocumentSuppressionSerializer(data=request.data)
            entree.is_valid(raise_exception=True)
            motif = entree.validated_data.get("motif", "")

        supprimer_document(
            document=document,
            utilisateur=request.user,
            motif=motif,
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentVersionsView(APIView):
    """`GET` et `POST /api/v1/ged/documents/{id}/versions/` — historique et révisions (3.6)."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAuthenticated, PermissionDocumentParCategorie]

    def _charger_document(self, request, pk) -> Document:
        document = get_object_or_404(queryset_documents_base(), pk=pk)
        self.check_object_permissions(request, document)
        return document

    @extend_schema(
        tags=TAGS,
        summary="Lister toutes les versions d'un document (de la plus récente à v1)",
        responses={200: VersionDocumentSerializer(many=True)},
    )
    def get(self, request, pk):
        document = self._charger_document(request, pk)
        versions = (
            VersionDocument.objects.select_related("auteur")
            .filter(document=document)
            .order_by("-numero_version")
        )
        return Response(
            VersionDocumentSerializer(versions, many=True, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=TAGS,
        summary="Déposer une nouvelle version v(N+1) avec note de révision obligatoire",
        request={"multipart/form-data": NouvelleVersionSerializer},
        responses={
            201: VersionDocumentSerializer,
            400: OpenApiResponse(description="Note de révision manquante ou fichier invalide."),
            413: OpenApiResponse(description="Taille du fichier supérieure à 50 Mo."),
            422: OpenApiResponse(description="Document automatique non modifiable manuellement."),
        },
    )
    def post(self, request, pk):
        document = self._charger_document(request, pk)
        entree = NouvelleVersionSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data

        version = ajouter_version(
            document=document,
            fichier=donnees["fichier"],
            auteur=request.user,
            commentaire=donnees["commentaire"],
            est_reference=donnees.get("est_reference"),
            est_appel_systeme=False,
            exiger_commentaire=True,
            request=request,
        )
        version = VersionDocument.objects.select_related("auteur").get(pk=version.pk)
        return Response(
            VersionDocumentSerializer(version, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


def _servir_fichier_version(
    *,
    request,
    document: Document,
    version: VersionDocument,
) -> FileResponse:
    if not version.fichier:
        raise NotFound(_("Le fichier de cette version est indisponible."))
    try:
        flux = version.fichier.open("rb")
    except FileNotFoundError as exc:
        raise NotFound(_("Le fichier demandé est introuvable sur le stockage.")) from exc

    nom_fichier = version.nom_fichier_affiche or f"{document.nom}_{version.numero}"
    journaliser_evenement_ged(
        action=ActionAudit.TELECHARGEMENT,
        document=document,
        utilisateur=request.user,
        details=f"Téléchargement {version.numero} ({nom_fichier})",
        request=request,
        extra={"version": version.numero, "nom_fichier": nom_fichier},
    )
    reponse = FileResponse(
        flux,
        as_attachment=True,
        filename=nom_fichier,
        content_type=version.mime_type or "application/octet-stream",
    )
    reponse["Cache-Control"] = "private, no-store"
    return reponse


class DocumentTelechargerView(APIView):
    """`GET /api/v1/ged/documents/{id}/telecharger/` — téléchargement de la version active."""

    permission_classes = [IsAuthenticated, PeutTelechargerDocument]

    @extend_schema(
        tags=TAGS,
        summary="Télécharger la version active d'un document GED",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        document = get_object_or_404(queryset_documents_base(), pk=pk)
        self.check_object_permissions(request, document)
        version = extraire_version_active(document)
        if version is None:
            raise NotFound(_("Aucune version disponible pour ce document."))
        return _servir_fichier_version(request=request, document=document, version=version)


class DocumentVersionTelechargerView(APIView):
    """`GET /api/v1/ged/documents/{id}/versions/{version_id}/telecharger/`."""

    permission_classes = [IsAuthenticated, PeutTelechargerDocument]

    @extend_schema(
        tags=TAGS,
        summary="Télécharger une version spécifique d'un document GED",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk, version_id):
        document = get_object_or_404(queryset_documents_base(), pk=pk)
        self.check_object_permissions(request, document)
        version = get_object_or_404(VersionDocument, pk=version_id, document=document)
        return _servir_fichier_version(request=request, document=document, version=version)
