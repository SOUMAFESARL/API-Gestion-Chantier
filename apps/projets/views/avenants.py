"""Les avenants au contrat d'un projet (30/10/2026)."""

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import peut_voir_montants
from apps.core.permissions import GardePermissionProjet
from apps.core.purger_montants import valider_ecriture_montant
from apps.projets.models import Avenant, Projet
from apps.projets.services.avenants import avenant_en_dict, enregistrer_avenant, retirer_avenant
from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture
from apps.projets.services.perimetres import exiger

__all__ = [
    "AvenantDetailView",
    "AvenantDocumentView",
    "AvenantOrdreServiceView",
    "ProjetAvenantsView",
]

TAGS = ["avenants"]


class AvenantCreationSerializer(serializers.Serializer):
    numero = serializers.CharField(max_length=30)
    date_signature = serializers.DateField()
    objet = serializers.CharField()
    annees_accordees = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        max_value=100,
        error_messages={
            "min_value": _("Le nombre d'années de prolongation ne peut pas être négatif.")
        },
    )
    mois_accordes = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        max_value=1200,
        error_messages={
            "min_value": _("Le nombre de mois de prolongation ne peut pas être négatif.")
        },
    )
    jours_accordes = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        max_value=3650,
        error_messages={
            "min_value": _("Le nombre de jours de prolongation ne peut pas être négatif.")
        },
    )
    montant = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        min_value=0,
        error_messages={"min_value": _("Le montant d'un avenant ne peut pas être négatif.")},
    )
    elements_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Vide : l'avenant porte sur le projet entier.",
    )
    document = serializers.FileField(
        required=True,
        allow_null=False,
        error_messages={
            "required": _("Le document d'avenant signé est obligatoire."),
            "null": _("Le document d'avenant signé est obligatoire."),
            "empty": _("Le document d'avenant signé ne peut pas être vide."),
        },
    )
    ordre_service = serializers.FileField(
        required=True,
        allow_null=False,
        error_messages={
            "required": _("L'ordre de service lié à l'avenant est obligatoire."),
            "null": _("L'ordre de service lié à l'avenant est obligatoire."),
            "empty": _("L'ordre de service lié à l'avenant ne peut pas être vide."),
        },
    )

    def validate_montant(self, value):
        request = self.context.get("request") if getattr(self, "context", None) else None
        return valider_ecriture_montant(value, request=request, champ="montant")


def _reponse(request, avenant):
    return avenant_en_dict(avenant, montants_visibles=peut_voir_montants(request.user, request))


class ProjetAvenantsView(APIView):
    """`GET`/`POST /api/v1/projets/{id}/avenants/` — les avenants du projet ; en enregistrer un."""

    parser_classes = [MultiPartParser, JSONParser]
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(tags=TAGS, summary="Avenants du projet", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        avenants = Avenant.objects.filter(projet=projet).prefetch_related("elements")
        return Response([_reponse(request, a) for a in avenants])

    @extend_schema(
        tags=TAGS,
        summary="Enregistrer un avenant signé",
        request={"multipart/form-data": AvenantCreationSerializer},
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        exiger(request.user, "projets.avenants_gerer", projet, request=request)
        verifier_statut_projet_pour_ecriture(projet)
        donnees = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if hasattr(request.data, "getlist") and "elements_ids" in request.data:
            donnees.setlist("elements_ids", request.data.getlist("elements_ids"))
        serializer = AvenantCreationSerializer(data=donnees, context={"request": request})
        serializer.is_valid(raise_exception=True)
        avenant = enregistrer_avenant(projet, **serializer.validated_data, auteur=request.user)
        return Response(_reponse(request, avenant), status=status.HTTP_201_CREATED)


class AvenantDetailView(APIView):
    """`GET`/`DELETE /api/v1/avenants/{id}/` — un avenant ; le retirer (enregistré par erreur)."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    def _avenant(self, request, pk):
        avenant = get_object_or_404(Avenant.objects.select_related("projet"), pk=pk)
        self.check_object_permissions(request, avenant.projet)
        return avenant

    @extend_schema(tags=TAGS, summary="Un avenant", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(_reponse(request, self._avenant(request, pk)))

    @extend_schema(tags=TAGS, summary="Retirer un avenant", responses={204: None})
    def delete(self, request, pk):
        avenant = self._avenant(request, pk)
        exiger(request.user, "projets.avenants_gerer", avenant.projet, request=request)
        retirer_avenant(avenant, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvenantDocumentView(APIView):
    """`GET /api/v1/avenants/{id}/document/` — le document signé joint à l'avenant."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        tags=TAGS,
        summary="Télécharger le document signé",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        avenant = get_object_or_404(Avenant.objects.select_related("projet"), pk=pk)
        self.check_object_permissions(request, avenant.projet)
        if not avenant.document:
            raise NotFound("Cet avenant n'a pas de document joint.")
        try:
            fichier = avenant.document.open("rb")
        except FileNotFoundError as exc:
            raise NotFound("Le document de l'avenant est indisponible.") from exc
        reponse = FileResponse(
            fichier,
            as_attachment=True,
            filename=avenant.document_nom or f"avenant-{avenant.numero}",
            content_type=avenant.document_type or "application/octet-stream",
        )
        reponse["Cache-Control"] = "private, no-store"
        return reponse


class AvenantOrdreServiceView(APIView):
    """`GET /api/v1/avenants/{id}/ordre-service/` — l'ordre de service joint à l'avenant."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        tags=TAGS,
        summary="Télécharger l'ordre de service de l'avenant",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        avenant = get_object_or_404(Avenant.objects.select_related("projet"), pk=pk)
        self.check_object_permissions(request, avenant.projet)
        if not avenant.ordre_service:
            raise NotFound("Cet avenant n'a pas d'ordre de service joint.")
        try:
            fichier = avenant.ordre_service.open("rb")
        except FileNotFoundError as exc:
            raise NotFound("L'ordre de service de l'avenant est indisponible.") from exc
        reponse = FileResponse(
            fichier,
            as_attachment=True,
            filename=avenant.ordre_service_nom or f"ordre-service-avenant-{avenant.numero}",
            content_type=avenant.ordre_service_type or "application/octet-stream",
        )
        reponse["Cache-Control"] = "private, no-store"
        return reponse
