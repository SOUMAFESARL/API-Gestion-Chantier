"""Vues pour les activités de travaux (MLD §6.3).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.permissions import MembreDuProjet, PermissionModule
from apps.projets.models import Activite, Lot
from apps.projets.serializers import ActiviteCreationSerializer, ActiviteSerializer

__all__ = ["ActiviteDetailView", "LotActiviteListCreateView"]

ERREURS_ACTIVITES = {
    401: OpenApiResponse(description="Authentification requise."),
    403: OpenApiResponse(description="Accès au projet parent refusé."),
    404: OpenApiResponse(description="Lot ou activité absent ou supprimé."),
}


class LotActiviteListCreateView(APIView):
    """Liste et création des activités pour un lot donné."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        return [IsAuthenticated(), MembreDuProjet()]

    @extend_schema(
        summary="Lister les activités d'un lot",
        tags=["activités"],
        responses={200: ActiviteSerializer(many=True), **ERREURS_ACTIVITES},
    )
    def get(self, request, lot_id):
        lot = get_object_or_404(Lot.objects.select_related("projet"), pk=lot_id)
        self.check_object_permissions(request, lot)
        activites = lot.activites.filter(supprime_le__isnull=True).order_by("ordre", "cree_le")
        return Response(
            ActiviteSerializer(activites.prefetch_related("equipe"), many=True).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Ajouter une activité sur un lot",
        tags=["activités"],
        request=ActiviteCreationSerializer,
        description=(
            "Activité rattachée au lot de l'URL. Tout utilisateur connecté ayant accès "
            "au projet peut créer une activité. Libellé obligatoire ; quantité par défaut 1, "
            "unité U, dates et équipe facultatives. Dépendance active du même projet. "
            "Budget facultatif en centimes FCFA pour les statistiques pondérées. "
            "equipe_ids contient des UUID de collaborateurs du projet ; les équipes de "
            "chantier se rattachent ensuite via l'API d'affectations. Avancement automatique "
            "à 0 à la création, jusqu'à 100 selon les quantités réalisées."
        ),
        examples=[
            OpenApiExample(
                "Activité minimale sans dates ni équipe",
                request_only=True,
                value={"libelle": "Terrassement des fondations"},
            ),
            OpenApiExample(
                "Nouvelle activité",
                request_only=True,
                value={
                    "libelle": "Carte_transport",
                    "quantite_prevue": "100.000",
                    "unite": "M2",
                    "date_debut_prevue": "2026-10-04",
                    "date_fin_prevue": "2026-10-11",
                    "dependance": None,
                    "equipe_ids": [],
                    "budget_initial_montant": 1000000,
                },
            ),
        ],
        responses={
            201: ActiviteSerializer,
            400: OpenApiResponse(description="Dates hors bornes du lot ou champs invalides."),
            **ERREURS_ACTIVITES,
        },
    )
    @transaction.atomic
    def post(self, request, lot_id):
        lot = get_object_or_404(
            Lot.objects.select_related("projet").select_for_update(of=("self",)), pk=lot_id
        )
        self.check_object_permissions(request, lot)
        if not lot.est_actif:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"lot": "Le lot est désactivé."})

        serializer = ActiviteCreationSerializer(
            data=request.data,
            context={"request": request, "lot": lot},
        )
        serializer.is_valid(raise_exception=True)
        activite = serializer.save()
        return Response(ActiviteSerializer(activite).data, status=status.HTTP_201_CREATED)


class ActiviteDetailView(APIView):
    """Détail et suppression logique d'une activité."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("DELETE", "PUT", "PATCH"):
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
        summary="Détail d'une activité",
        tags=["activités"],
        description=(
            "Accès au projet et permission de lecture du module Projets requis. "
            "Cette route permet de consulter (GET) et de supprimer logiquement "
            "(DELETE) une activité. La modification (PUT/PATCH), l'activation et "
            "la désactivation ne sont pas encore exposées par cette API."
        ),
        responses={200: ActiviteSerializer, **ERREURS_ACTIVITES},
    )
    def get(self, request, pk):
        activite = get_object_or_404(Activite.objects.select_related("lot", "lot__projet"), pk=pk)
        self.check_object_permissions(request, activite)
        return Response(ActiviteSerializer(activite).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer logiquement une activité",
        tags=["activités"],
        description=(
            "Accès au projet et permission d'écriture du module Projets requis. "
            "Suppression logique : l'activité est conservée en base mais retirée "
            "des résultats courants. Retourne 204 sans corps de réponse. "
            "Cette opération est distincte d'une désactivation."
        ),
        responses={204: OpenApiResponse(description="Activité supprimée."), **ERREURS_ACTIVITES},
    )
    def delete(self, request, pk):
        activite = get_object_or_404(Activite.objects.select_related("lot", "lot__projet"), pk=pk)
        self.check_object_permissions(request, activite)
        activite.delete(utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
