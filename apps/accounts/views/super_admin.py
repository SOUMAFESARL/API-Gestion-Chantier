"""Vues Super Admin — plateforme CCD Digital."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.serializers.impersonation import (
    ErreurPlateformeResponseSerializer,
    VerifierAccesSuperAdminResponseSerializer,
)


class VerifierAccesSuperAdminView(APIView):
    """Vérifie l'accès au panneau Super Admin (accès ouvert sans restriction d'adresse IP)."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["admins"],
        summary="Vérifier l'accès au panneau Super Admin",
        description=(
            "Vérifie l'accès au panneau Super Admin. L'accès est ouvert à tous "
            "sans restriction d'adresse IP."
        ),
        auth=[],
        responses={
            200: VerifierAccesSuperAdminResponseSerializer,
        },
    )
    def get(self, request):
        ip = extraire_ip_client(request)
        return Response(
            {
                "statut": "autorise",
                "ip": ip,
                "message": "Accès autorisé pour l'administration de la plateforme.",
            },
            status=status.HTTP_200_OK,
        )
