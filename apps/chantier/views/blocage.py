"""Vues pour la gestion des blocages de chantier."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chantier.models import Blocage
from apps.chantier.permissions import (
    PeutConsulterRapports,
    PeutRedigerRapports,
    PeutValiderRapports,
)
from apps.chantier.serializers.blocage import (
    BlocageCreateSerializer,
    BlocageResolutionSerializer,
    BlocageSerializer,
    BlocageUpdateSerializer,
)
from apps.chantier.services.blocage import (
    creer_blocage,
    modifier_blocage,
    prendre_en_charge_blocage,
    resoudre_blocage,
)
from apps.projets.models import Lot, Projet

__all__ = [
    "BlocageDetailView",
    "BlocagePrendreEnChargeView",
    "BlocageResoudreView",
    "ProjetBlocageListCreateView",
]


class ProjetBlocageListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/{projet_id}/blocages/`."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), PeutRedigerRapports()]
        return [IsAuthenticated(), PeutConsulterRapports()]

    @extend_schema(
        summary="Lister les blocages d'un projet",
        description="Retourne la liste des blocages et incidents du projet, ordonnés du plus récent au plus ancien.",
        responses={200: BlocageSerializer(many=True)},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=projet_id,
        )
        self.check_object_permissions(request, projet)

        qs = Blocage.objects.filter(
            projet=projet,
            supprime_le__isnull=True,
        ).select_related("projet", "lot", "ouvert_par", "resolu_par")

        statut_filtre = request.query_params.get("statut")
        if statut_filtre:
            qs = qs.filter(statut=statut_filtre)

        severite_filtre = request.query_params.get("severite")
        if severite_filtre:
            qs = qs.filter(severite=severite_filtre)

        serializer = BlocageSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un blocage de chantier",
        description="Déclare un nouveau point bloquant sur le projet et planifie un recalcul de santé.",
        request=BlocageCreateSerializer,
        responses={201: BlocageSerializer},
    )
    def post(self, request, projet_id):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=projet_id,
        )
        self.check_object_permissions(request, projet)

        serializer = BlocageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lot = None
        lot_id = serializer.validated_data.get("lot_id")
        if lot_id:
            lot = get_object_or_404(Lot.objects.filter(projet=projet, supprime_le__isnull=True), pk=lot_id)

        blocage = creer_blocage(
            projet=projet,
            titre=serializer.validated_data["titre"],
            severite=serializer.validated_data["severite"],
            auteur=request.user,
            description=serializer.validated_data.get("description", ""),
            lot=lot,
        )
        return Response(BlocageSerializer(blocage).data, status=status.HTTP_201_CREATED)


class BlocageDetailView(APIView):
    """`GET` et `PATCH /api/v1/blocages/{pk}/`."""

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), PeutRedigerRapports()]
        return [IsAuthenticated(), PeutConsulterRapports()]

    @extend_schema(
        summary="Consulter un blocage",
        description="Renvoie les détails d'un blocage de chantier.",
        responses={200: BlocageSerializer},
    )
    def get(self, request, pk):
        blocage = get_object_or_404(
            Blocage.objects.filter(supprime_le__isnull=True).select_related(
                "projet", "lot", "ouvert_par", "resolu_par"
            ),
            pk=pk,
        )
        self.check_object_permissions(request, blocage)
        return Response(BlocageSerializer(blocage).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un blocage",
        description="Met à jour les informations d'un blocage (titre, sévérité, etc.) et recalcule la santé.",
        request=BlocageUpdateSerializer,
        responses={200: BlocageSerializer},
    )
    def patch(self, request, pk):
        blocage = get_object_or_404(
            Blocage.objects.filter(supprime_le__isnull=True).select_related("projet"),
            pk=pk,
        )
        self.check_object_permissions(request, blocage)

        serializer = BlocageUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        blocage_modifie = modifier_blocage(
            blocage=blocage,
            modifie_par=request.user,
            **serializer.validated_data,
        )
        return Response(BlocageSerializer(blocage_modifie).data, status=status.HTTP_200_OK)


class BlocagePrendreEnChargeView(APIView):
    """`POST /api/v1/blocages/{pk}/prendre-en-charge/`."""

    permission_classes = [IsAuthenticated, PeutRedigerRapports]

    @extend_schema(
        summary="Prendre en charge un blocage",
        description="Bascule le statut du blocage à PRIS_EN_CHARGE.",
        request=None,
        responses={200: BlocageSerializer},
    )
    def post(self, request, pk):
        blocage = get_object_or_404(
            Blocage.objects.filter(supprime_le__isnull=True).select_related("projet"),
            pk=pk,
        )
        self.check_object_permissions(request, blocage)

        blocage_mis_a_jour = prendre_en_charge_blocage(
            blocage=blocage,
            utilisateur=request.user,
        )
        return Response(BlocageSerializer(blocage_mis_a_jour).data, status=status.HTTP_200_OK)


class BlocageResoudreView(APIView):
    """`POST /api/v1/blocages/{pk}/resoudre/`."""

    permission_classes = [IsAuthenticated, PeutValiderRapports]

    @extend_schema(
        summary="Résoudre un blocage",
        description="Résout le blocage et retire sa pénalité de l'indice de santé.",
        request=BlocageResolutionSerializer,
        responses={200: BlocageSerializer},
    )
    def post(self, request, pk):
        blocage = get_object_or_404(
            Blocage.objects.filter(supprime_le__isnull=True).select_related("projet"),
            pk=pk,
        )
        self.check_object_permissions(request, blocage)

        serializer = BlocageResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        blocage_resolu = resoudre_blocage(
            blocage=blocage,
            utilisateur=request.user,
            commentaire_resolution=serializer.validated_data.get("commentaire", ""),
        )
        return Response(BlocageSerializer(blocage_resolu).data, status=status.HTTP_200_OK)
