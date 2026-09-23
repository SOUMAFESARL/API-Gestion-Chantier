"""Lecture des factures de l'entreprise active dans le schema public."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.billing.models import Facture
from apps.billing.serializers.facture import FactureSerializer
from apps.billing.services.facture import generer_pdf_facture
from apps.core.enums import RoleGlobal
from apps.core.permissions import RoleRequis


class FactureBaseView(GenericAPIView):
    serializer_class = FactureSerializer
    permission_classes = [
        IsAuthenticated,
        RoleRequis.pour(
            RoleGlobal.ADMIN,
            RoleGlobal.DIRECTEUR_GENERAL,
            RoleGlobal.DIRECTEUR_FINANCIER,
        ),
    ]

    def get_queryset(self):
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
        summary="Lister les factures de l'entreprise", responses=FactureSerializer(many=True)
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
    @extend_schema(summary="Consulter une facture", responses=FactureSerializer)
    def get(self, request, pk):
        with schema_context(get_public_schema_name()):
            facture = get_object_or_404(self.get_queryset(), pk=pk)
            return Response(self.get_serializer(facture).data)


class FacturePDFView(FactureBaseView):
    @extend_schema(
        summary="Telecharger une facture PDF",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        with schema_context(get_public_schema_name()):
            facture = get_object_or_404(self.get_queryset(), pk=pk)
            contenu = generer_pdf_facture(self.get_serializer(facture).data)
        response = HttpResponse(contenu, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="facture-{facture.pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
