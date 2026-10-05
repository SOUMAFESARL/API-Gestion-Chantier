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
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.permissions import MembreDuProjet, PermissionModule
from apps.projets.models import Lot, Projet
from apps.projets.serializers.lot import (
    ActivationSerializer,
    LotCreationSerializer,
    LotModificationSerializer,
    LotResponseSerializer,
)
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
            "Chaque lot expose son UUID et le UUID parent dans projet_id, le compteur "
            "activites_count et l'avancement réalisé calculé de 0 à 100. "
            "La liste comprend les lots actifs et désactivés, hors lots supprimés. "
            "Le champ est_actif indique l'état d'activation du lot. "
            "Modifier ou supprimer via /api/v1/lots/{id}/ ; activer ou désactiver "
            "via PATCH /api/v1/lots/{id}/activation/."
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
            "Nom, mode d'exécution et bordereau obligatoires ; budget et dates "
            "prévues et réelles facultatifs (YYYY-MM-DD ou null). "
            "Code et ordre générés automatiquement. Budget en centimes de FCFA. "
            "Le projet est celui de l'URL ; ne pas envoyer projet ni id_projet. "
            "Avancement automatique à 0 tant qu'aucune activité n'est réalisée."
            " Statut d'évolution facultatif : toute chaîne non vide envoyée par le frontend."
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
                    "statut": "En cours",
                    "motif": "Démarrage des travaux validé",
                    "mode_execution": "REGIE",
                    "type_bordereau": "FORFAIT",
                    "budget_initial_montant": None,
                    "date_debut_prevue": None,
                    "date_fin_prevue": None,
                    "date_debut_reelle": None,
                    "date_fin_reelle": None,
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


ERREURS_MUTATION_LOT = {
    **ERREURS_LOTS,
    400: OpenApiResponse(
        description="Champs invalides ou opération incompatible avec les activités du lot."
    ),
}


class LotDetailView(APIView):
    """Lecture, modification partielle et suppression logique d'un lot."""

    def get_permissions(self):
        niveau = (
            NiveauAcces.LECTURE
            if self.request.method in ("GET", "HEAD", "OPTIONS")
            else NiveauAcces.ECRITURE
        )
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, niveau)(),
            MembreDuProjet(),
        ]

    def obtenir_lot(self, request, pk, verrou=False):
        queryset = Lot.objects.select_related("projet").filter(projet__supprime_le__isnull=True)
        lot = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(request, lot)
        if verrou:
            get_object_or_404(Projet.objects.select_for_update(), pk=lot.projet_id)
            lot = get_object_or_404(queryset.select_for_update(of=("self",)), pk=pk)
        return lot

    @extend_schema(
        tags=["lots"],
        summary="Détail d'un lot",
        responses={200: LotResponseSerializer, **ERREURS_LOTS},
    )
    def get(self, request, pk):
        return Response(LotResponseSerializer(self.obtenir_lot(request, pk)).data)

    @extend_schema(
        tags=["lots"],
        summary="Modifier un lot",
        description=(
            "Modification partielle ; accès au projet et permission d'écriture requis. "
            "Code, projet, ordre et baseline immuables. Dates compatibles avec les "
            "activités existantes. Dates prévisionnelles déjà renseignées : "
            "utilisez la reprogrammation avec motif et justification (RG-11)."
        ),
        request=LotModificationSerializer,
        responses={200: LotResponseSerializer, **ERREURS_MUTATION_LOT},
        examples=[
            OpenApiExample("Renommer le lot", value={"nom": "Fondations"}, request_only=True),
            OpenApiExample("Statut libre", value={"statut": "Terminé"}, request_only=True),
        ],
    )
    @transaction.atomic
    def patch(self, request, pk):
        lot = self.obtenir_lot(request, pk, verrou=True)
        serializer = LotModificationSerializer(lot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lot_sauvegarde = serializer.save()
        if lot.projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=lot.projet_id,
                declencheur_type="LOT_MODIFICATION",
                declencheur_id=lot.id,
            )
        return Response(LotResponseSerializer(lot_sauvegarde).data)

    @extend_schema(
        tags=["lots"],
        summary="Supprimer logiquement un lot",
        description=(
            "Permission d'écriture et accès au projet requis. Refus 400 si des "
            "activités non supprimées existent. Aucune suppression physique."
        ),
        responses={
            204: OpenApiResponse(description="Lot supprimé, réponse sans corps."),
            **ERREURS_MUTATION_LOT,
        },
    )
    @transaction.atomic
    def delete(self, request, pk):
        lot = self.obtenir_lot(request, pk, verrou=True)
        if lot.activites.exists():
            raise ValidationError(
                {"lot": "Supprimez les activités du lot avant de le supprimer, ou désactivez-le."}
            )
        projet_id = lot.projet_id
        lot.delete(utilisateur=request.user)
        if projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=projet_id,
                declencheur_type="LOT_SUPPRESSION",
                declencheur_id=lot.id,
            )
        return Response(status=204)


class LotActivationView(LotDetailView):
    http_method_names = ["patch", "options"]

    @extend_schema(
        tags=["lots"],
        summary="Activer ou désactiver un lot",
        description=(
            "Permission d'écriture et accès au projet requis. Opération idempotente, "
            "sans modification de l'état des activités. Un lot désactivé refuse les "
            "nouvelles activités."
        ),
        request=ActivationSerializer,
        responses={200: LotResponseSerializer, **ERREURS_MUTATION_LOT},
        examples=[
            OpenApiExample("Désactiver", value={"est_actif": False}, request_only=True),
            OpenApiExample("Activer", value={"est_actif": True}, request_only=True),
        ],
    )
    @transaction.atomic
    def patch(self, request, pk):
        lot = self.obtenir_lot(request, pk, verrou=True)
        serializer = ActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot.est_actif = serializer.validated_data["est_actif"]
        lot.save(update_fields=["est_actif", "modifie_le"])
        if lot.projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=lot.projet_id,
                declencheur_type="LOT_ACTIVATION",
                declencheur_id=lot.id,
            )
        return Response(LotResponseSerializer(lot).data)
