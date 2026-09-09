from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tiers.models import Tiers
from apps.tiers.serializers import TiersCreationSerializer, TiersSerializer

__all__ = ["TiersDetailView", "TiersListCreateView"]


class TiersListCreateView(APIView):
    """`GET` et `POST /api/v1/tiers/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les tiers",
        responses={200: TiersSerializer(many=True)},
    )
    def get(self, request):
        qs = Tiers.objects.filter(est_actif=True).prefetch_related("roles")
        serializer = TiersSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un tiers",
        request=TiersCreationSerializer,
        responses={201: TiersSerializer},
    )
    def post(self, request):
        serializer = TiersCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tiers = serializer.save()
        retour = TiersSerializer(tiers)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class TiersDetailView(APIView):
    """`GET` et `PATCH /api/v1/tiers/<uuid:pk>/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'un tiers",
        responses={200: TiersSerializer},
    )
    def get(self, request, pk):
        tiers = get_object_or_404(Tiers.objects.prefetch_related("roles"), pk=pk)
        return Response(TiersSerializer(tiers).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un tiers",
        request=TiersCreationSerializer,
        responses={200: TiersSerializer},
    )
    def patch(self, request, pk):
        tiers = get_object_or_404(Tiers, pk=pk)
        serializer = TiersCreationSerializer(tiers, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tiers = serializer.save()
        return Response(TiersSerializer(tiers).data, status=status.HTTP_200_OK)
