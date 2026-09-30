"""Vues pour les activités de travaux (MLD §6.3).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.permissions import MembreDuProjet, PermissionModule
from apps.projets.models import Activite, Lot
from apps.projets.serializers import ActiviteCreationSerializer, ActiviteSerializer

__all__ = ["ActiviteDetailView", "LotActiviteListCreateView"]


class LotActiviteListCreateView(APIView):
    """Liste et création des activités pour un lot donné."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
                MembreDuProjet(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
            MembreDuProjet(),
        ]

    @extend_schema(
        summary="Lister les activités d'un lot",
        tags=["activités"],
        responses={200: ActiviteSerializer(many=True)},
    )
    def get(self, request, lot_id):
        lot = get_object_or_404(Lot.objects.select_related("projet"), pk=lot_id)
        self.check_object_permissions(request, lot)
        activites = lot.activites.filter(supprime_le__isnull=True).order_by("ordre", "cree_le")
        return Response(ActiviteSerializer(activites, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Ajouter une activité sur un lot",
        tags=["activités"],
        request=ActiviteCreationSerializer,
        responses={
            201: ActiviteSerializer,
            400: OpenApiResponse(description="Dates hors bornes du lot ou champs invalides."),
            403: OpenApiResponse(description="Accès non autorisé au lot/projet."),
        },
    )
    def post(self, request, lot_id):
        lot = get_object_or_404(Lot.objects.select_related("projet"), pk=lot_id)
        self.check_object_permissions(request, lot)

        serializer = ActiviteCreationSerializer(
            data=request.data,
            context={"request": request, "lot": lot},
        )
        serializer.is_valid(raise_exception=True)
        activite = serializer.save()
        return Response(ActiviteSerializer(activite).data, status=status.HTTP_201_CREATED)


class ActiviteDetailView(APIView):
    """Détail et suppression logique d'une activité."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("DELETE", "PUT", "PATCH"):
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
                MembreDuProjet(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
            MembreDuProjet(),
        ]

    @extend_schema(
        summary="Détail d'une activité",
        tags=["activités"],
        responses={200: ActiviteSerializer},
    )
    def get(self, request, pk):
        activite = get_object_or_404(Activite.objects.select_related("lot", "lot__projet"), pk=pk)
        self.check_object_permissions(request, activite)
        return Response(ActiviteSerializer(activite).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer une activité",
        tags=["activités"],
        responses={204: OpenApiResponse(description="Activité supprimée.")},
    )
    def delete(self, request, pk):
        activite = get_object_or_404(Activite.objects.select_related("lot", "lot__projet"), pk=pk)
        self.check_object_permissions(request, activite)
        activite.delete(utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
