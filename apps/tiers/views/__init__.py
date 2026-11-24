"""Vues API pour l'application tiers."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import APermission
from apps.core.ip_restriction import extraire_ip_client
from apps.tiers.models import Tiers
from apps.tiers.selectors import lister_tiers, nombre_projets_par_tiers
from apps.tiers.serializers import (
    TiersCreationSerializer,
    TiersDetailSerializer,
    TiersSerializer,
)
from apps.tiers.services import creer_tiers, modifier_tiers, supprimer_tiers

__all__ = ["TiersDetailView", "TiersListCreateView"]


class TiersListCreateView(APIView):
    """`GET` et `POST /api/v1/tiers/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [
                IsAuthenticated(),
                APermission.pour("tiers.ecrire")(),
            ]
        return [
            IsAuthenticated(),
            APermission.pour("tiers.lire")(),
        ]

    @extend_schema(
        summary="Lister les tiers",
        tags=["tiers"],
        parameters=[
            OpenApiParameter(
                "role",
                str,
                description="Filtre par rôle (code unique ou liste séparée par virgules).",
            ),
            OpenApiParameter(
                "type_tiers",
                str,
                description="Filtre par type de tiers : ENTREPRISE ou PERSONNE.",
            ),
            OpenApiParameter(
                "est_actif",
                str,
                description="Filtre d'activité : true (défaut), false, ou all / tous.",
            ),
            OpenApiParameter(
                "recherche",
                str,
                description=(
                    "Recherche insensible à la casse (raison sociale, téléphone, email, "
                    "ville, RCCM, NIF). Alias : search."
                ),
            ),
        ],
        responses={200: TiersSerializer(many=True)},
    )
    def get(self, request):
        recherche = (
            request.query_params.get("recherche") or request.query_params.get("search") or ""
        )
        qs = lister_tiers(
            role=request.query_params.get("role"),
            type_tiers=request.query_params.get("type_tiers"),
            est_actif=request.query_params.get("est_actif", "true"),
            recherche=recherche,
        )
        tiers_liste = list(qs)
        nombres = nombre_projets_par_tiers([t.pk for t in tiers_liste])
        serializer = TiersSerializer(
            tiers_liste,
            many=True,
            context={"request": request, "nombres_projets": nombres},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un tiers",
        tags=["tiers"],
        request=TiersCreationSerializer,
        responses={201: TiersDetailSerializer},
    )
    def post(self, request):
        serializer = TiersCreationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tiers = creer_tiers(
            serializer.validated_data,
            auteur=request.user,
            adresse_ip=extraire_ip_client(request),
            appareil=request.headers.get("User-Agent", ""),
        )
        retour = TiersDetailSerializer(tiers, context={"request": request})
        return Response(retour.data, status=status.HTTP_201_CREATED)


class TiersDetailView(APIView):
    """`GET`, `PATCH` et `DELETE /api/v1/tiers/<uuid:pk>/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [
                IsAuthenticated(),
                APermission.pour("tiers.ecrire")(),
            ]
        return [
            IsAuthenticated(),
            APermission.pour("tiers.lire")(),
        ]

    @extend_schema(
        summary="Détail d'un tiers",
        tags=["tiers"],
        responses={200: TiersDetailSerializer},
    )
    def get(self, request, pk):
        tiers = get_object_or_404(Tiers.objects.prefetch_related("roles"), pk=pk)
        return Response(
            TiersDetailSerializer(tiers, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Modifier un tiers",
        tags=["tiers"],
        request=TiersCreationSerializer,
        responses={200: TiersDetailSerializer},
    )
    def patch(self, request, pk):
        tiers = get_object_or_404(Tiers.objects.prefetch_related("roles"), pk=pk)
        serializer = TiersCreationSerializer(
            tiers, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        tiers = modifier_tiers(
            tiers,
            serializer.validated_data,
            auteur=request.user,
            adresse_ip=extraire_ip_client(request),
            appareil=request.headers.get("User-Agent", ""),
        )
        return Response(
            TiersDetailSerializer(tiers, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Supprimer un tiers",
        tags=["tiers"],
        description=(
            "Suppression logique du tiers s'il n'est référencé par aucun projet, élément de "
            "découpage, équipe de chantier, main-d'œuvre ou bon de commande. Sinon, renvoie 409 "
            "(code `tiers_reference`) afin de proposer sa désactivation."
        ),
        responses={
            204: OpenApiResponse(description="Tiers supprimé logiquement."),
            409: OpenApiResponse(description="Tiers référencé : suppression bloquée."),
        },
    )
    def delete(self, request, pk):
        tiers = get_object_or_404(Tiers.objects.prefetch_related("roles"), pk=pk)
        supprimer_tiers(
            tiers,
            auteur=request.user,
            adresse_ip=extraire_ip_client(request),
            appareil=request.headers.get("User-Agent", ""),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
