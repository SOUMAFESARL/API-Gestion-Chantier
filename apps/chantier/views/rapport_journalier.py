"""Vues pour l'application chantier — gestion des rapports journaliers."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chantier.filters import RapportJournalierFilter
from apps.chantier.models import RapportJournalier
from apps.chantier.permissions import (
    PeutConsulterRapports,
    PeutRedigerRapports,
    PeutValiderRapports,
)
from apps.chantier.selectors.rapport_journalier import rapport_par_id, rapports_liste
from apps.chantier.serializers.rapport_journalier import (
    RapportJournalierCreateSerializer,
    RapportJournalierDetailSerializer,
    RapportJournalierListSerializer,
    RapportJournalierUpdateSerializer,
    RapportRejetSerializer,
    RapportValidationSerializer,
)
from apps.chantier.services.rapport_journalier import (
    rejeter_rapport_journalier,
    soumettre_rapport_journalier,
    valider_rapport_journalier,
)
from apps.core.pagination import PaginationStandard

__all__ = [
    "RapportDetailView",
    "RapportListCreateView",
    "RapportRejeterView",
    "RapportSoumettreView",
    "RapportValiderView",
]


class RapportListCreateView(APIView):
    """`GET /api/v1/rapports/` (liste paginée) et `POST /api/v1/rapports/` (création)."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), PeutRedigerRapports()]
        return [IsAuthenticated(), PeutConsulterRapports()]

    @extend_schema(
        summary="Lister les rapports de chantier",
        description="Retourne la liste paginée des rapports journaliers, filtrable par projet, lot, statut, dates et auteur.",
        responses={200: RapportJournalierListSerializer(many=True)},
    )
    def get(self, request):
        qs = rapports_liste()
        filtre = RapportJournalierFilter(request.GET, queryset=qs)
        paginatrice = PaginationStandard()
        page = paginatrice.paginate_queryset(filtre.qs, request, view=self)
        serializer = RapportJournalierListSerializer(page, many=True)
        return paginatrice.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Créer un rapport journalier",
        description="Enregistre un nouveau rapport de chantier en mode BROUILLON ou SOUMIS direct.",
        request=RapportJournalierCreateSerializer,
        responses={201: RapportJournalierDetailSerializer},
    )
    def post(self, request):
        serializer = RapportJournalierCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        rapport = serializer.save()
        retour = RapportJournalierDetailSerializer(rapport)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class RapportDetailView(APIView):
    """`GET` et `PATCH /api/v1/rapports/<uuid:pk>/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), PeutRedigerRapports()]
        return [IsAuthenticated(), PeutConsulterRapports()]

    @extend_schema(
        summary="Détail complet d'un rapport de chantier",
        responses={200: RapportJournalierDetailSerializer},
    )
    def get(self, request, pk):
        rapport = get_object_or_404(
            RapportJournalier.objects.select_related(
                "projet", "lot", "auteur", "valide_par"
            ),
            pk=pk,
        )
        self.check_object_permissions(request, rapport)
        return Response(RapportJournalierDetailSerializer(rapport).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un rapport de chantier",
        description="Mise à jour partielle (auto-save ou édition de brouillon). Refusé si déjà approuvé.",
        request=RapportJournalierUpdateSerializer,
        responses={200: RapportJournalierDetailSerializer},
    )
    def patch(self, request, pk):
        rapport = get_object_or_404(RapportJournalier, pk=pk)
        self.check_object_permissions(request, rapport)
        serializer = RapportJournalierUpdateSerializer(
            rapport, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        rapport_modifie = serializer.save()
        rapport_recharge = rapport_par_id(rapport_modifie.id) or rapport_modifie
        return Response(
            RapportJournalierDetailSerializer(rapport_recharge).data,
            status=status.HTTP_200_OK,
        )


class RapportSoumettreView(APIView):
    """`POST /api/v1/rapports/<uuid:pk>/soumettre/`."""

    permission_classes = [IsAuthenticated, PeutRedigerRapports]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Soumettre un rapport journalier",
        request=None,
        description="Passe le rapport au statut SOUMIS pour revue par le Conducteur de Travaux.",
        responses={200: RapportJournalierDetailSerializer},
    )
    def post(self, request, pk):
        rapport = get_object_or_404(RapportJournalier, pk=pk)
        self.check_object_permissions(request, rapport)
        rapport = soumettre_rapport_journalier(rapport=rapport, utilisateur=request.user)
        rapport_recharge = rapport_par_id(rapport.id) or rapport
        return Response(
            RapportJournalierDetailSerializer(rapport_recharge).data,
            status=status.HTTP_200_OK,
        )


class RapportValiderView(APIView):
    """`POST /api/v1/rapports/<uuid:pk>/valider/`."""

    permission_classes = [IsAuthenticated, PeutValiderRapports]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Valider et approuver un rapport journalier",
        description="Approuve définitivement le rapport journalier (action réservée CT/CP/DG).",
        request=RapportValidationSerializer,
        responses={200: RapportJournalierDetailSerializer},
    )
    def post(self, request, pk):
        rapport = get_object_or_404(RapportJournalier, pk=pk)
        self.check_object_permissions(request, rapport)
        serializer = RapportValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rapport = valider_rapport_journalier(
            rapport=rapport,
            utilisateur=request.user,
            commentaire=serializer.validated_data.get("commentaire", ""),
        )
        rapport_recharge = rapport_par_id(rapport.id) or rapport
        return Response(
            RapportJournalierDetailSerializer(rapport_recharge).data,
            status=status.HTTP_200_OK,
        )


class RapportRejeterView(APIView):
    """`POST /api/v1/rapports/<uuid:pk>/rejeter/`."""

    permission_classes = [IsAuthenticated, PeutValiderRapports]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Rejeter un rapport journalier avec motif obligatoire",
        description="Rejette le rapport journalier en exigeant un motif d'au moins 20 caractères.",
        request=RapportRejetSerializer,
        responses={200: RapportJournalierDetailSerializer},
    )
    def post(self, request, pk):
        rapport = get_object_or_404(RapportJournalier, pk=pk)
        self.check_object_permissions(request, rapport)
        serializer = RapportRejetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rapport = rejeter_rapport_journalier(
            rapport=rapport,
            utilisateur=request.user,
            motif=serializer.validated_data["motif"],
        )
        rapport_recharge = rapport_par_id(rapport.id) or rapport
        return Response(
            RapportJournalierDetailSerializer(rapport_recharge).data,
            status=status.HTTP_200_OK,
        )
