"""Vues REST internes des liens de partage externe temporaire 72 h (tâche 3.9)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ged.models import Document, PartageDocument
from apps.ged.permissions import peut_partager_document
from apps.ged.serializers.partages import PartageCreationSerializer, PartageDocumentSerializer
from apps.ged.services.partages import creer_partage_document, revoquer_partage_document

__all__ = [
    "DocumentPartagesView",
    "PartageDetailView",
]

TAGS = ["ged"]


class DocumentPartagesView(APIView):
    """`GET` et `POST /api/v1/ged/documents/{id}/partages/` — réservé à AD / DG / DO / CP."""

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def _verifier_document(self, request, pk) -> Document:
        document = get_object_or_404(Document.objects.select_related("projet", "entreprise"), pk=pk)
        autorise, motif = peut_partager_document(request.user, document, request=request)
        if not autorise:
            raise PermissionDenied(motif)
        return document

    @extend_schema(
        tags=TAGS,
        summary="Lister les liens de partage externe 72 h d'un document",
        responses={200: PartageDocumentSerializer(many=True)},
    )
    def get(self, request, pk):
        document = self._verifier_document(request, pk)
        partages = (
            PartageDocument.objects.select_related("cree_par")
            .filter(document=document)
            .order_by("-cree_le")
        )
        return Response(
            PartageDocumentSerializer(partages, many=True).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=TAGS,
        summary="Générer un lien de partage externe temporaire valable 72 h",
        request=PartageCreationSerializer,
        responses={201: PartageDocumentSerializer},
    )
    def post(self, request, pk):
        document = self._verifier_document(request, pk)
        entree = PartageCreationSerializer(data=request.data or {})
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data

        partage = creer_partage_document(
            document=document,
            utilisateur=request.user,
            destinataire=donnees.get("destinataire", ""),
            note=donnees.get("note", ""),
            request=request,
        )
        return Response(
            PartageDocumentSerializer(partage).data,
            status=status.HTTP_201_CREATED,
        )


class PartageDetailView(APIView):
    """`DELETE /api/v1/ged/partages/{partage_id}/` — révocation immédiate (AD / DG / DO / CP)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAGS,
        summary="Révoquer immédiatement un lien de partage externe",
        responses={204: None},
    )
    def delete(self, request, partage_id):
        partage = get_object_or_404(
            PartageDocument.objects.select_related("document__projet", "document__entreprise"),
            pk=partage_id,
        )
        autorise, motif = peut_partager_document(request.user, partage.document, request=request)
        if not autorise:
            raise PermissionDenied(motif)

        revoquer_partage_document(partage=partage, utilisateur=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
