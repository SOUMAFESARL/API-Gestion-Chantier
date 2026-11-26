"""Vues REST du journal d'audit GED (consultations, dépôts, partages, suppressions — tâche 3.8)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.contexte import exiger_entreprise
from apps.ged.models import Document
from apps.ged.permissions import peut_voir_historique_document
from apps.ged.selectors.historique import (
    lister_historique_document,
    lister_historique_global_ged,
)
from apps.ged.serializers.historique import EvenementAuditGedSerializer
from apps.projets.models import Projet

__all__ = [
    "DocumentHistoriqueView",
    "HistoriqueGlobalGedView",
]

TAGS = ["ged"]


class DocumentHistoriqueView(APIView):
    """`GET /api/v1/ged/documents/{id}/historique/` — réservé à AD / DG / DO / CP."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAGS,
        summary="Consulter le journal d'audit d'un document GED (AD / DG / DO / CP)",
        responses={200: EvenementAuditGedSerializer(many=True)},
    )
    def get(self, request, pk):
        document = get_object_or_404(Document.tous_objets.select_related("projet"), pk=pk)
        autorise, motif = peut_voir_historique_document(
            request.user,
            document=document,
            request=request,
        )
        if not autorise:
            raise PermissionDenied(motif)

        entrees = lister_historique_document(
            document_id=document.pk,
            entreprise_id=document.entreprise_id,
        )
        return Response(
            EvenementAuditGedSerializer(entrees, many=True).data,
            status=status.HTTP_200_OK,
        )


class HistoriqueGlobalGedView(APIView):
    """`GET /api/v1/ged/historique/` — journal global des accès/suppressions (AD/DG/DO/CP)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAGS,
        summary="Consulter l'historique global des consultations et suppressions GED",
        parameters=[
            OpenApiParameter("projet", OpenApiTypes.UUID, description="Filtrer par projet"),
            OpenApiParameter(
                "action", OpenApiTypes.STR, description="Ex. SUPPRESSION, CONSULTATION"
            ),
        ],
        responses={200: EvenementAuditGedSerializer(many=True)},
    )
    def get(self, request):
        projet_id = (request.query_params.get("projet") or "").strip() or None
        action = (request.query_params.get("action") or "").strip() or None

        projet = None
        if projet_id:
            projet = get_object_or_404(Projet, pk=projet_id)

        autorise, motif = peut_voir_historique_document(
            request.user,
            projet=projet,
            request=request,
        )
        if not autorise:
            raise PermissionDenied(motif)

        entrees = lister_historique_global_ged(
            user=request.user,
            entreprise_id=exiger_entreprise(),
            projet_id=str(projet.pk) if projet else None,
            action=action,
            request=request,
        )
        return Response(
            EvenementAuditGedSerializer(entrees, many=True).data,
            status=status.HTTP_200_OK,
        )
