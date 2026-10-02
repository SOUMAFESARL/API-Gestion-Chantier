from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import MembreDuProjet
from apps.projets.models import Projet
from apps.projets.serializers.statistiques import StatistiquesProjetSerializer
from apps.projets.services.statistiques import statistiques_lots


class ProjetStatistiquesView(APIView):
    permission_classes = [IsAuthenticated, MembreDuProjet]

    @extend_schema(
        tags=["activités"],
        summary="Statistiques des lots et activités du projet",
        description=(
            "Statistiques calculées à chaque lecture. Lots et activités actifs non supprimés. "
            "Pondération par budget si toutes les activités ont un budget positif, "
            "sinon moyenne uniforme. Retard : fin passée et réalisation inférieure à 100 %."
        ),
        responses={
            200: StatistiquesProjetSerializer,
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
        examples=[
            OpenApiExample(
                "Deux activités pondérées par budget",
                response_only=True,
                value={
                    "lots_count": 2,
                    "activites_count": 2,
                    "avancement_pondere": 12.5,
                    "ponderation": "BUDGET",
                    "activites_en_retard": 1,
                    "budget_activites_montant": 40000,
                },
            )
        ],
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        lots = projet.lots.prefetch_related("activites")
        return Response(statistiques_lots(lots))
