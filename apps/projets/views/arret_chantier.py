"""Vues pour la gestion des arrêts de chantier."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import APermission
from apps.core.permissions import MembreDuProjet
from apps.projets.models import ArretChantier, Projet
from apps.projets.serializers.arret_chantier import (
    ArretChantierCreateSerializer,
    ArretChantierSerializer,
    ArretChantierUpdateSerializer,
)
from apps.projets.services.arret_chantier import (
    declarer_arret_chantier,
    modifier_arret_chantier,
    supprimer_arret_chantier,
)

__all__ = [
    "ArretChantierDetailView",
    "ProjetArretChantierListCreateView",
]


class ProjetArretChantierListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/{projet_id}/arrets-chantier/`."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                APermission.pour("projets.changer_statut")(),
                MembreDuProjet(),
            ]
        return [
            IsAuthenticated(),
            APermission.pour("projets.lire")(),
            MembreDuProjet(),
        ]

    @extend_schema(
        summary="Lister les arrêts de chantier d'un projet",
        description="Retourne l'ensemble des arrêts de chantier déclarés sur le projet.",
        responses={200: ArretChantierSerializer(many=True)},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=projet_id,
        )
        self.check_object_permissions(request, projet)

        arrets = ArretChantier.objects.filter(
            projet=projet,
            supprime_le__isnull=True,
        ).select_related("declare_par").order_by("-date_debut")
        serializer = ArretChantierSerializer(arrets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Déclarer un arrêt de chantier",
        description="Déclare un arrêt de chantier ou une période de suspension. Planifie un recalcul d'indice de santé.",
        request=ArretChantierCreateSerializer,
        responses={201: ArretChantierSerializer},
    )
    def post(self, request, projet_id):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=projet_id,
        )
        self.check_object_permissions(request, projet)

        serializer = ArretChantierCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        arret = declarer_arret_chantier(
            projet=projet,
            date_debut=serializer.validated_data["date_debut"],
            date_fin=serializer.validated_data.get("date_fin"),
            motif=serializer.validated_data["motif"],
            auteur=request.user,
        )
        output_serializer = ArretChantierSerializer(arret)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class ArretChantierDetailView(APIView):
    """`PATCH` et `DELETE /api/v1/arrets-chantier/{pk}/`."""

    permission_classes = [
        IsAuthenticated,
        APermission.pour("projets.changer_statut"),
        MembreDuProjet,
    ]

    @extend_schema(
        summary="Modifier un arrêt de chantier",
        description="Met à jour un arrêt de chantier (motif, dates) et recalcule l'indice de santé si nécessaire.",
        request=ArretChantierUpdateSerializer,
        responses={200: ArretChantierSerializer},
    )
    def patch(self, request, pk):
        arret = get_object_or_404(
            ArretChantier.objects.filter(supprime_le__isnull=True).select_related("projet"),
            pk=pk,
        )
        self.check_object_permissions(request, arret)

        serializer = ArretChantierUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        arret_modifie = modifier_arret_chantier(
            arret=arret,
            utilisateur=request.user,
            **serializer.validated_data,
        )
        return Response(ArretChantierSerializer(arret_modifie).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer un arrêt de chantier",
        description="Supprime logiquement un arrêt de chantier et recalcule l'indice de santé.",
        responses={204: None},
    )
    def delete(self, request, pk):
        arret = get_object_or_404(
            ArretChantier.objects.filter(supprime_le__isnull=True).select_related("projet"),
            pk=pk,
        )
        self.check_object_permissions(request, arret)

        supprimer_arret_chantier(arret=arret, utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
