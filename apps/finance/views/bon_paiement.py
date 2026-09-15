"""Vues pour la gestion des bons de paiement."""

import uuid

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.models import BonPaiement
from apps.finance.serializers import (
    BonPaiementCreationSerializer,
    BonPaiementSerializer,
)

__all__ = ["BonPaiementDetailView", "BonPaiementListCreateView"]


class BonPaiementListCreateView(APIView):
    """`GET` et `POST /api/v1/finance/bons-paiement/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]
    serializer_class = BonPaiementSerializer

    @extend_schema(
        summary="Lister les bons de paiement",
        description="Renvoie la liste des bons de paiement de l'entreprise avec filtrage optionnel.",
        parameters=[
            OpenApiParameter(
                name="projet_id",
                type=uuid.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtrer par identifiant du chantier / projet.",
            ),
            OpenApiParameter(
                name="statut",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtrer par statut (ex: BROUILLON, A_VALIDER, A_SIGNER, SIGNE, PAYE, REJETE).",
            ),
            OpenApiParameter(
                name="beneficiaire_id",
                type=uuid.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtrer par identifiant du tiers bénéficiaire (tâcheron ou sous-traitant).",
            ),
        ],
        responses={200: BonPaiementSerializer(many=True)},
    )
    def get(self, request):
        qs = (
            BonPaiement.objects.filter(supprime_le__isnull=True)
            .select_related("projet", "lot", "beneficiaire")
            .prefetch_related("signatures__signataire")
            .order_by("-cree_le")
        )

        projet_id = request.query_params.get("projet_id")
        if projet_id:
            try:
                qs = qs.filter(projet_id=uuid.UUID(str(projet_id)))
            except (ValueError, TypeError):
                pass

        statut_param = request.query_params.get("statut")
        if statut_param:
            qs = qs.filter(statut=statut_param)

        beneficiaire_id = request.query_params.get("beneficiaire_id")
        if beneficiaire_id:
            try:
                qs = qs.filter(beneficiaire_id=uuid.UUID(str(beneficiaire_id)))
            except (ValueError, TypeError):
                pass

        serializer = BonPaiementSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un bon de paiement",
        description="Émet un nouveau bon de paiement pour un sous-traitant ou tâcheron.",
        request=BonPaiementCreationSerializer,
        responses={201: BonPaiementSerializer},
    )
    def post(self, request):
        serializer = BonPaiementCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bon = serializer.save()
        return Response(BonPaiementSerializer(bon).data, status=status.HTTP_201_CREATED)


class BonPaiementDetailView(APIView):
    """`GET` et `PATCH /api/v1/finance/bons-paiement/{id}/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]
    serializer_class = BonPaiementSerializer

    @extend_schema(
        summary="Détail d'un bon de paiement",
        description="Renvoie la fiche complète d'un bon de paiement avec l'historique de ses signatures.",
        responses={200: BonPaiementSerializer, 404: dict},
    )
    def get(self, request, pk):
        bon = get_object_or_404(
            BonPaiement.objects.filter(supprime_le__isnull=True)
            .select_related("projet", "lot", "beneficiaire")
            .prefetch_related("signatures__signataire"),
            pk=pk,
        )
        return Response(BonPaiementSerializer(bon).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un bon de paiement",
        description="Met à jour les informations d'un bon de paiement non encore réglé.",
        request=BonPaiementCreationSerializer,
        responses={200: BonPaiementSerializer, 404: dict},
    )
    def patch(self, request, pk):
        bon = get_object_or_404(BonPaiement, pk=pk, supprime_le__isnull=True)
        serializer = BonPaiementCreationSerializer(bon, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        bon = serializer.save()
        return Response(BonPaiementSerializer(bon).data, status=status.HTTP_200_OK)
