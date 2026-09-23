"""Validation des inscriptions par un super admin du schema public."""

from django.db import connection
from django.shortcuts import get_object_or_404
from django_tenants.utils import get_public_schema_name
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.serializers.inscriptions import (
    DemandeInscriptionAdminSerializer,
    RefusInscriptionSerializer,
)
from apps.platform_admin.services.inscriptions import decider_inscription
from apps.tenants.models import DemandeInscription


class SuperAdminPublic(BasePermission):
    def has_permission(self, request, view):
        return (
            connection.schema_name == get_public_schema_name()
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.is_superuser
        )


ERREURS = {
    401: OpenApiResponse(description="Authentification requise."),
    403: OpenApiResponse(description="Super admin du schema public requis."),
    404: OpenApiResponse(description="Demande introuvable."),
    409: OpenApiResponse(description="Etat incompatible avec cette decision."),
}


class DemandesBaseView(GenericAPIView):
    permission_classes = [IsAuthenticated, SuperAdminPublic]
    serializer_class = DemandeInscriptionAdminSerializer
    queryset = DemandeInscription.objects.all().order_by("-cree_le", "-pk")
    filter_backends = []


class DemandesInscriptionView(DemandesBaseView):
    @extend_schema(
        tags=["Validation des inscriptions"],
        summary="Lister les demandes d'inscription",
        description=(
            "Jeton de connexion super admin requis. "
            "Filtrer A_VALIDER pour les decisions en attente."
        ),
        parameters=[OpenApiParameter("statut", str, enum=DemandeInscription.Statut.values)],
        responses={200: DemandeInscriptionAdminSerializer(many=True), **ERREURS},
    )
    def get(self, request):
        demandes = self.get_queryset()
        statut = request.query_params.get("statut")
        if statut:
            if statut not in DemandeInscription.Statut.values:
                raise ValidationError({"statut": "Statut inconnu."})
            demandes = demandes.filter(statut=statut)
        page = self.paginate_queryset(demandes)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class DemandeInscriptionDetailView(DemandesBaseView):
    @extend_schema(
        tags=["Validation des inscriptions"],
        summary="Consulter une demande",
        responses={200: DemandeInscriptionAdminSerializer, **ERREURS},
    )
    def get(self, request, pk):
        return Response(self.get_serializer(get_object_or_404(self.get_queryset(), pk=pk)).data)


class ApprouverInscriptionView(DemandesBaseView):
    @extend_schema(
        tags=["Validation des inscriptions"],
        summary="Approuver une inscription verifiee",
        request=None,
        responses={202: DemandeInscriptionAdminSerializer, **ERREURS},
    )
    def post(self, request, pk):
        demande = decider_inscription(
            pk, request.user, approuver=True, adresse_ip=extraire_ip_client(request)
        )
        return Response(self.get_serializer(demande).data, status=202)


class RefuserInscriptionView(DemandesBaseView):
    @extend_schema(
        tags=["Validation des inscriptions"],
        summary="Refuser une inscription verifiee",
        request=RefusInscriptionSerializer,
        responses={
            200: DemandeInscriptionAdminSerializer,
            400: OpenApiResponse(description="Motif requis."),
            **ERREURS,
        },
    )
    def post(self, request, pk):
        serializer = RefusInscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        demande = decider_inscription(
            pk,
            request.user,
            approuver=False,
            motif=serializer.validated_data["motif"],
            adresse_ip=extraire_ip_client(request),
        )
        return Response(self.get_serializer(demande).data)
