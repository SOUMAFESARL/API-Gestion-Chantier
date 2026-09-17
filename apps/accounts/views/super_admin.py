"""Vues Super Admin — plateforme CCD Digital."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.ip_restriction import extraire_ip_client


class VerifierAccesSuperAdminView(APIView):
    """Vérifie si l'adresse IP appelante est autorisée à accéder au panneau Super Admin.

    Cette vue est protégée en amont par `RestrictionIPPlateformeMiddleware`.
    Si la requête parvient ici, c'est que l'IP est autorisée.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Vérifier l'accès IP au panneau Super Admin",
        description="Renvoie le statut d'autorisation de l'adresse IP appelante.",
        responses={200: dict},
    )
    def get(self, request):
        ip = extraire_ip_client(request)
        return Response(
            {
                "statut": "autorise",
                "ip": ip,
                "message": "Adresse IP autorisée pour l'administration de la plateforme.",
            },
            status=status.HTTP_200_OK,
        )
