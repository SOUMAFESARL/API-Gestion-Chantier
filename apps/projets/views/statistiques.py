from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Projet
from apps.projets.serializers.statistiques import StatistiquesProjetSerializer
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.statistiques import statistiques_arbre


class ProjetStatistiquesView(APIView):
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        tags=["découpage"],
        summary="Statistiques de l'arbre du projet",
        description=(
            "Statistiques calculées à chaque lecture sur les cases actives de l'arbre. "
            "Physique pondéré par les montants (décisions v1.2, §8) ; nul quand aucun montant "
            "n'est connu. Retard d'une feuille : fin passée et réalisation inférieure à 100 %."
        ),
        responses={
            200: StatistiquesProjetSerializer,
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
        examples=[
            OpenApiExample(
                "Arbre pondéré par les montants",
                response_only=True,
                value={
                    "cases_count": 12,
                    "feuilles_count": 8,
                    "avancement_pondere": 55.7,
                    "avancement_partiel": False,
                    "ponderation": "MONTANT",
                    "feuilles_en_retard": 1,
                },
            )
        ],
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        data = statistiques_arbre(charger_arbre(projet))
        from apps.core.droits import peut_voir_montants
        from apps.core.purger_montants import purger_montants_recursif

        if not peut_voir_montants(request.user, request):
            data = purger_montants_recursif(data)
        return Response(data)
