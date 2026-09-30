"""Vues pour la reprogrammation de dates et l'historique (US-033, RG-11).

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

from apps.core.enums import ModuleChoix, NiveauAcces, RoleGlobal
from apps.core.permissions import MembreDuProjet, PermissionModule
from apps.projets.models import (
    Activite,
    HistoriqueDate,
    Lot,
    MotifReport,
    Projet,
    TypeObjetHistorique,
)
from apps.projets.serializers import (
    HistoriqueDateSerializer,
    MotifReportCreationSerializer,
    MotifReportSerializer,
    ReprogrammationRequestSerializer,
    ReprogrammationResponseSerializer,
)
from apps.projets.services.reprogrammation import reprogrammer_date_instance

__all__ = [
    "ActiviteHistoriqueDatesView",
    "ActiviteReprogrammerView",
    "LotHistoriqueDatesView",
    "LotReprogrammerView",
    "MotifReportListCreateView",
    "ProjetHistoriqueDatesView",
    "ProjetReprogrammerView",
]


class MotifReportListCreateView(APIView):
    """Liste et création dynamique des motifs de report de dates."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
        ]

    @extend_schema(
        summary="Lister les motifs de report actifs",
        tags=["reprogrammation"],
        responses={200: MotifReportSerializer(many=True)},
    )
    def get(self, request):
        motifs = MotifReport.objects.filter(supprime_le__isnull=True, est_actif=True)
        return Response(MotifReportSerializer(motifs, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un nouveau motif dynamique de report",
        tags=["reprogrammation"],
        request=MotifReportCreationSerializer,
        responses={
            201: MotifReportSerializer,
            400: OpenApiResponse(description="Données invalides ou code en doublon."),
        },
    )
    def post(self, request):
        serializer = MotifReportCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        motif = serializer.save(cree_par=request.user)
        return Response(MotifReportSerializer(motif).data, status=status.HTTP_201_CREATED)


class BaseReprogrammerView(APIView):
    """Classe de base pour les actions de reprogrammation de dates."""

    parser_classes = [JSONParser]
    permission_classes = [
        IsAuthenticated,
        PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE),
        MembreDuProjet,
    ]

    def executer_reprogrammation(self, request, instance, type_objet: str):
        self.check_object_permissions(request, instance)
        serializer = ReprogrammationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        resultat = reprogrammer_date_instance(
            instance=instance,
            nouvelle_date_fin=data["date_fin_prevue"],
            nouvelle_date_debut=data.get("date_debut_prevue"),
            motif_id=str(data["motif_id"]),
            justification=data["justification"],
            auteur=request.user,
        )

        resultat["type_objet"] = type_objet
        rep_serializer = ReprogrammationResponseSerializer(resultat)
        return Response(rep_serializer.data, status=status.HTTP_200_OK)


class ProjetReprogrammerView(BaseReprogrammerView):
    """Reprogrammation de la date prévisionnelle d'un Projet (US-033)."""

    @extend_schema(
        summary="Reprogrammer les dates prévisionnelles d'un projet",
        tags=["reprogrammation"],
        request=ReprogrammationRequestSerializer,
        responses={
            200: ReprogrammationResponseSerializer,
            400: OpenApiResponse(description="Justification < 30 car., motif invalide ou dépassement."),
            403: OpenApiResponse(description="Accès non autorisé au projet."),
            404: OpenApiResponse(description="Projet introuvable."),
        },
    )
    def post(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        return self.executer_reprogrammation(request, projet, TypeObjetHistorique.PROJET)


class LotReprogrammerView(BaseReprogrammerView):
    """Reprogrammation de la date prévisionnelle d'un Lot de travaux."""

    @extend_schema(
        summary="Reprogrammer les dates prévisionnelles d'un lot",
        tags=["reprogrammation"],
        request=ReprogrammationRequestSerializer,
        responses={
            200: ReprogrammationResponseSerializer,
            400: OpenApiResponse(description="Justification < 30 car., motif invalide ou dépassement."),
            403: OpenApiResponse(description="Accès non autorisé au lot/projet."),
            404: OpenApiResponse(description="Lot introuvable."),
        },
    )
    def post(self, request, pk):
        lot = get_object_or_404(Lot.objects.select_related("projet"), pk=pk)
        return self.executer_reprogrammation(request, lot, TypeObjetHistorique.LOT)


class ActiviteReprogrammerView(BaseReprogrammerView):
    """Reprogrammation de la date prévisionnelle d'une Activité."""

    @extend_schema(
        summary="Reprogrammer les dates prévisionnelles d'une activité",
        tags=["reprogrammation"],
        request=ReprogrammationRequestSerializer,
        responses={
            200: ReprogrammationResponseSerializer,
            400: OpenApiResponse(description="Justification < 30 car., motif invalide ou dépassement."),
            403: OpenApiResponse(description="Accès non autorisé à l'activité/projet."),
            404: OpenApiResponse(description="Activité introuvable."),
        },
    )
    def post(self, request, pk):
        activite = get_object_or_404(Activite.objects.select_related("lot", "lot__projet"), pk=pk)
        return self.executer_reprogrammation(request, activite, TypeObjetHistorique.ACTIVITE)


class BaseHistoriqueDatesView(APIView):
    """Consultation de la traçabilité des dates (HistoriqueDate)."""

    permission_classes = [
        IsAuthenticated,
        PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE),
        MembreDuProjet,
    ]

    def lister_historique(self, request, instance, filtre_kwargs):
        self.check_object_permissions(request, instance)
        historiques = (
            HistoriqueDate.objects.filter(**filtre_kwargs)
            .select_related("motif", "auteur")
            .order_by("-cree_le")
        )
        return Response(HistoriqueDateSerializer(historiques, many=True).data, status=status.HTTP_200_OK)


class ProjetHistoriqueDatesView(BaseHistoriqueDatesView):
    """Historique des décalages d'un projet."""

    @extend_schema(
        summary="Consulter l'historique des dates d'un projet",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        return self.lister_historique(
            request,
            projet,
            {"projet": projet, "type_objet": TypeObjetHistorique.PROJET},
        )


class LotHistoriqueDatesView(BaseHistoriqueDatesView):
    """Historique des décalages d'un lot."""

    @extend_schema(
        summary="Consulter l'historique des dates d'un lot",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request, pk):
        lot = get_object_or_404(Lot.objects.select_related("projet"), pk=pk)
        return self.lister_historique(
            request,
            lot,
            {"lot": lot, "type_objet": TypeObjetHistorique.LOT},
        )


class ActiviteHistoriqueDatesView(BaseHistoriqueDatesView):
    """Historique des décalages d'une activité."""

    @extend_schema(
        summary="Consulter l'historique des dates d'une activité",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request, pk):
        activite = get_object_or_404(Activite.objects.select_related("lot", "lot__projet"), pk=pk)
        return self.lister_historique(
            request,
            activite,
            {"activite": activite, "type_objet": TypeObjetHistorique.ACTIVITE},
        )
