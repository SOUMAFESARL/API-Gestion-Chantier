"""Notification de facturation de l'entreprise authentifiee."""

from django_tenants.utils import get_public_schema_name
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.serializers.expiration import NotificationExpirationSerializer
from apps.billing.services.expiration import ROLES_FACTURATION, notifications_expiration
from apps.core.permissions import RoleRequis


class NotificationsExpirationView(APIView):
    permission_classes = [IsAuthenticated, RoleRequis.pour(*ROLES_FACTURATION)]

    @extend_schema(
        tags=["Notifications d'abonnement"],
        summary="Consulter l'alerte d'expiration de son abonnement",
        description=(
            "Roles AD, DG, DF. Tableau vide ou une alerte calculee a chaque lecture, "
            "des J-7 et jusqu'au renouvellement. Paliers J-7, J-3, J-1, J0. "
            "Les essais gratuits conservent leur circuit de relance existant. "
            "Aucun email n'est envoye par cette requete."
        ),
        responses={
            200: NotificationExpirationSerializer(many=True),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Role non autorise ou schema public."),
        },
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            raise PermissionDenied("Une entreprise cliente est requise.")
        response = Response(
            NotificationExpirationSerializer(notifications_expiration(tenant), many=True).data
        )
        response["Cache-Control"] = "private, no-store"
        return response
