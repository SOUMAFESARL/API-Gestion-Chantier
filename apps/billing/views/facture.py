"""Lecture des factures de l'entreprise active dans le schema public."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.billing.models import Facture
from apps.billing.serializers.facture import FactureSerializer
from apps.billing.services.facture import generer_pdf_facture
from apps.core.enums import RoleGlobal
from apps.core.permissions import RoleRequis

ERREURS_FACTURE = {
    401: OpenApiResponse(description="Jeton JWT absent ou invalide."),
    403: OpenApiResponse(description="Role non autorise ou schema public."),
    404: OpenApiResponse(description="Facture introuvable dans cette entreprise."),
}
DESCRIPTION_FACTURE = (
    "Jeton JWT de l'entreprise requis. Roles autorises : AD, DG, DF. "
    "Les montants JSON sont en centimes XOF. Les factures sont creees par "
    "l'initiation du paiement puis marquees PAYEE apres confirmation CinetPay."
)


class FacturePDFRenderer(JSONRenderer):
    """Accepte le PDF ; les erreurs DRF conservent leur enveloppe JSON."""

    media_type = "application/pdf"
    format = "pdf"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if renderer_context and renderer_context.get("response") is not None:
            renderer_context["response"]["Content-Type"] = "application/json"
        return super().render(data, accepted_media_type, renderer_context)


class FactureBaseView(GenericAPIView):
    serializer_class = FactureSerializer
    filter_backends = []
    permission_classes = [
        IsAuthenticated,
        RoleRequis.pour(
            RoleGlobal.ADMIN,
            RoleGlobal.DIRECTEUR_GENERAL,
            RoleGlobal.DIRECTEUR_FINANCIER,
        ),
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Facture.objects.none()
        tenant = getattr(self.request, "tenant", None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            raise PermissionDenied(
                "Selectionnez une entreprise cliente pour consulter ses factures."
            )
        return (
            Facture.objects.filter(entreprise_id=tenant.pk)
            .prefetch_related("paiements")
            .order_by("-date_emission", "-cree_le", "-pk")
        )


class FactureListeView(FactureBaseView):
    @extend_schema(
        summary="Lister les factures de l'entreprise",
        description=DESCRIPTION_FACTURE,
        tags=["Factures d'abonnement"],
        parameters=[OpenApiParameter("statut", OpenApiTypes.STR, enum=Facture.Statut.values)],
        responses={
            200: FactureSerializer(many=True),
            **ERREURS_FACTURE,
            400: OpenApiResponse(description="Statut de facture invalide."),
        },
    )
    def get(self, request):
        with schema_context(get_public_schema_name()):
            factures = self.get_queryset()
            statut = request.query_params.get("statut")
            if statut:
                if statut not in Facture.Statut.values:
                    raise ValidationError({"statut": "Statut de facture inconnu."})
                factures = factures.filter(statut=statut)
            page = self.paginate_queryset(factures)
            return self.get_paginated_response(self.get_serializer(page, many=True).data)


class FactureDetailView(FactureBaseView):
    @extend_schema(
        summary="Consulter une facture",
        description=DESCRIPTION_FACTURE,
        tags=["Factures d'abonnement"],
        responses={200: FactureSerializer, **ERREURS_FACTURE},
    )
    def get(self, request, pk):
        with schema_context(get_public_schema_name()):
            facture = get_object_or_404(self.get_queryset(), pk=pk)
            return Response(self.get_serializer(facture).data)


class FacturePDFView(FactureBaseView):
    renderer_classes = [JSONRenderer, FacturePDFRenderer]

    @extend_schema(
        summary="Telecharger une facture PDF",
        description=DESCRIPTION_FACTURE + " Document joint, sans cache public.",
        tags=["Factures d'abonnement"],
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            **{(code, "application/json"): valeur for code, valeur in ERREURS_FACTURE.items()},
        },
    )
    def get(self, request, pk):
        with schema_context(get_public_schema_name()):
            facture = get_object_or_404(self.get_queryset(), pk=pk)
            contenu = generer_pdf_facture(self.get_serializer(facture).data)
        response = HttpResponse(contenu, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="facture-{facture.pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
