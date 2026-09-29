from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.permissions import (
    MembreDuProjet,
    PermissionModule,
    filtrer_queryset_par_affectations,
)
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

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
        ]

    @extend_schema(
        summary="Lister les projets",
        responses={200: ProjetSerializer(many=True)},
    )
    def get(self, request):
        qs = (
            Projet.objects.all()
            .select_related("client", "chef_projet", "conducteur_travaux", "cree_par")
            .prefetch_related("lots")
        )
        qs = filtrer_queryset_par_affectations(
            qs, request.user, champ_projet="id", request=request
        )
        serializer = ProjetSerializer(qs, many=True, context={"request": request})
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
        projet_charge = (
            Projet.objects.select_related("client", "chef_projet", "conducteur_travaux", "cree_par")
            .prefetch_related("lots")
            .get(pk=projet.pk)
        )
        retour = ProjetSerializer(projet_charge, context={"request": request})
        return Response(retour.data, status=status.HTTP_201_CREATED)


class ProjetDetailView(APIView):
    """`GET` et `PATCH /api/v1/projets/<uuid:pk>/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
                MembreDuProjet(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
            MembreDuProjet(),
        ]

    @extend_schema(
        summary="Détail d'un projet",
        responses={200: ProjetSerializer},
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.select_related(
                "client", "chef_projet", "conducteur_travaux", "cree_par"
            ).prefetch_related("lots"),
            pk=pk,
        )
        self.check_object_permissions(request, projet)
        return Response(
            ProjetSerializer(projet, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Modifier un projet",
        request=ProjetCreationSerializer,
        responses={200: ProjetSerializer},
    )
    def patch(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        serializer = ProjetCreationSerializer(
            projet, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        projet_charge = (
            Projet.objects.select_related("client", "chef_projet", "conducteur_travaux", "cree_par")
            .prefetch_related("lots")
            .get(pk=projet.pk)
        )
        retour = ProjetSerializer(projet_charge, context={"request": request})
        return Response(retour.data, status=status.HTTP_200_OK)
