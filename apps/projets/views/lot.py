"""Liste et création : appartenance au projet, indépendamment du rôle global."""

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    extend_schema_field,
)
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import MembreDuProjet
from apps.projets.models import Projet
from apps.projets.serializers.lot import LotCreationSerializer, LotResponseSerializer
from apps.projets.services.lots import creer_lots, lire_excel, modele_excel

ERREURS_LOTS = {
    401: OpenApiResponse(description="Authentification requise."),
    403: OpenApiResponse(description="Utilisateur sans accès à ce projet."),
    404: OpenApiResponse(description="Projet absent ou supprimé."),
}


class ProjetLotListCreateView(APIView):
    permission_classes = [IsAuthenticated, MembreDuProjet]

    @extend_schema(
        tags=["lots"],
        summary="Lister les lots d'un projet",
        description=(
            "Chaque lot expose son UUID et le UUID parent dans projet, le compteur "
            "activites_count et l'avancement réalisé calculé de 0 à 100."
        ),
        responses={200: LotResponseSerializer(many=True), **ERREURS_LOTS},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        return Response(
            LotResponseSerializer(projet.lots.prefetch_related("activites"), many=True).data
        )

    @extend_schema(
        tags=["lots"],
        summary="Créer un lot dans un projet existant",
        description=(
            "Tout utilisateur connecté ayant accès au projet peut créer plusieurs lots. "
            "Nom, mode d'exécution et bordereau obligatoires ; budget et dates facultatifs. "
            "Code et ordre générés automatiquement. Budget en centimes de FCFA. "
            "Le projet est celui de l'URL ; ne pas envoyer projet ni id_projet. "
            "Avancement automatique à 0 tant qu'aucune activité n'est réalisée."
        ),
        request=LotCreationSerializer,
        responses={
            201: LotResponseSerializer,
            400: OpenApiResponse(description="Champs du lot invalides."),
            **ERREURS_LOTS,
        },
        examples=[
            OpenApiExample(
                "Nouveau lot",
                request_only=True,
                value={
                    "nom": "Gros œuvre",
                    "mode_execution": "REGIE",
                    "type_bordereau": "FORFAIT",
                    "budget_initial_montant": None,
                    "date_debut_prevue": None,
                    "date_fin_prevue": None,
                },
            )
        ],
    )
    @transaction.atomic
    def post(self, request, pk):
        projet = get_object_or_404(Projet.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, projet)
        serializer = LotCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot = creer_lots(projet, [serializer.validated_data], request.user)[0]
        return Response(LotResponseSerializer(lot).data, status=201)


@extend_schema_field(OpenApiTypes.BINARY)
class FichierLotsField(serializers.FileField):
    """Fichier binaire à téléverser dans Swagger."""


class LotImportSerializer(serializers.Serializer):
    fichier = FichierLotsField(help_text="Classeur .xlsx, maximum 5 Mo, 1000 lots.")


class ProjetLotImportView(APIView):
    permission_classes = [IsAuthenticated, MembreDuProjet]
    parser_classes = [MultiPartParser]

    @extend_schema(
        tags=["lots"],
        summary="Importer plusieurs lots depuis Excel",
        description=(
            "Multipart : fichier .xlsx de 5 Mo maximum, 1000 lignes maximum. "
            "Seul nom est exigé ; REGIE et FORFAIT sont les valeurs par défaut. "
            "Budget Excel en FCFA. Dates YYYY-MM-DD ou cellules date Excel. "
            "Première feuille seulement. Toute ligne invalide annule l'import."
        ),
        request=LotImportSerializer,
        responses={
            201: LotResponseSerializer(many=True),
            400: OpenApiResponse(description="Classeur ou lignes invalides ; aucun lot créé."),
            **ERREURS_LOTS,
        },
    )
    @transaction.atomic
    def post(self, request, pk):
        projet = get_object_or_404(Projet.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, projet)
        serializer = LotImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = lire_excel(serializer.validated_data["fichier"])
        lots = creer_lots(projet, donnees, request.user)
        return Response(LotResponseSerializer(lots, many=True).data, status=201)


class ProjetLotModeleView(APIView):
    permission_classes = [IsAuthenticated, MembreDuProjet]

    @extend_schema(
        tags=["lots"],
        summary="Télécharger le modèle Excel des lots",
        responses={
            (
                200,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ): OpenApiTypes.BINARY,
            **ERREURS_LOTS,
        },
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        response = HttpResponse(
            modele_excel(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="modele-lots.xlsx"'
        return response
