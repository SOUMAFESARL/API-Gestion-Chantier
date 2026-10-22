"""Vue API du réglage de l'en-tête et du pied des documents PDF.

Route : `GET` et `PATCH /api/v1/entreprise/documents/`, déclarée avec les autres
routes `entreprise/` dans `apps/tenants/urls_tenant.py`.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.core.droits import APermission
from apps.core.enums import ActionAudit
from apps.core.exceptions import RequeteRefusee
from apps.core.ip_restriction import extraire_ip_client
from apps.projets.models.parametres_documents import ParametresDocuments
from apps.projets.serializers.parametres_documents import (
    DocumentsReponseSerializer,
    ParametresDocumentsSerializer,
)
from apps.projets.services.parametres_documents import resoudre_documents

__all__ = ["ParametresDocumentsView"]


def _corps(request, tenant, parametres: ParametresDocuments) -> dict:
    return {
        "reglage": ParametresDocumentsSerializer(parametres).data,
        **resoudre_documents(parametres, tenant, request),
    }


def _tenant(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or tenant.schema_name == "public":
        raise RequeteRefusee(_("Aucun tenant résolu."))
    return tenant


class ParametresDocumentsView(APIView):
    """`GET` et `PATCH /api/v1/entreprise/documents/` — en-tête et pied des PDF."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "POST"):
            return [IsAuthenticated(), APermission.pour("administration.documents_gerer")()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Lire l'en-tête et le pied des documents",
        description=(
            "Renvoie le réglage et les lignes résolues avec les valeurs de l'entreprise "
            "(RCCM, NIF, adresse, téléphone principal, email…), prêtes à imprimer. "
            "Ouvert à tout utilisateur authentifié : chaque PDF en a besoin. "
            "Une mention sans valeur est omise."
        ),
        responses={200: DocumentsReponseSerializer},
        tags=["entreprise"],
    )
    def get(self, request):
        tenant = _tenant(request)
        return Response(_corps(request, tenant, ParametresDocuments.courant()))

    @extend_schema(
        summary="Modifier l'en-tête et le pied des documents",
        description=(
            "Modification partielle. Un code de mention inconnu est refusé (400). "
            "Exige la permission administration.documents_gerer (DG, AD)."
        ),
        request=ParametresDocumentsSerializer,
        responses={
            200: DocumentsReponseSerializer,
            400: OpenApiResponse(description="Code de mention inconnu ou donnée invalide."),
            403: OpenApiResponse(description="Permission non accordée."),
        },
        tags=["entreprise"],
    )
    def patch(self, request):
        tenant = _tenant(request)
        with transaction.atomic():
            parametres = ParametresDocuments.courant()
            serializer = ParametresDocumentsSerializer(
                instance=parametres, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)

            valeur_avant = dict(ParametresDocumentsSerializer(parametres).data)
            for champ, valeur in serializer.validated_data.items():
                setattr(parametres, champ, valeur)
            parametres.save(update_fields=[*serializer.validated_data, "modifie_le"])
            valeur_apres = dict(ParametresDocumentsSerializer(parametres).data)

            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="parametres_documents",
                entite_id=parametres.pk,
                utilisateur_id=request.user.pk,
                valeur_avant=valeur_avant,
                valeur_apres=valeur_apres,
                adresse_ip=extraire_ip_client(request) or None,
                appareil=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
            )

        return Response(_corps(request, tenant, parametres), status=status.HTTP_200_OK)
