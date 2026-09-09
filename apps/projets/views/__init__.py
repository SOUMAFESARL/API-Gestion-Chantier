from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projets.models import Projet
from apps.projets.serializers import ProjetCreationSerializer, ProjetSerializer
from apps.projets.views.meteo import MeteoProjetView, ReferentielVillesView
from apps.projets.views.override import ProjetPermissionsRolesView
from apps.projets.views.tableau_de_bord import TableauDeBordView

__all__ = [
    "MeteoProjetView",
    "ProjetDetailView",
    "ProjetListCreateView",
    "ProjetPermissionsRolesView",
    "ReferentielVillesView",
    "TableauDeBordView",
]


class ProjetListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les projets",
        responses={200: ProjetSerializer(many=True)},
    )
    def get(self, request):
        qs = Projet.objects.all().select_related("client", "chef_projet")
        serializer = ProjetSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un projet",
        request=ProjetCreationSerializer,
        responses={201: ProjetSerializer},
    )
    def post(self, request):
        serializer = ProjetCreationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        retour = ProjetSerializer(projet)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class ProjetDetailView(APIView):
    """`GET` et `PATCH /api/v1/projets/<uuid:pk>/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'un projet",
        responses={200: ProjetSerializer},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet.objects.select_related("client", "chef_projet"), pk=pk)
        return Response(ProjetSerializer(projet).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un projet",
        request=ProjetCreationSerializer,
        responses={200: ProjetSerializer},
    )
    def patch(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        serializer = ProjetCreationSerializer(
            projet, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        retour = ProjetSerializer(projet)
        return Response(retour.data, status=status.HTTP_200_OK)
