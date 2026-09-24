"""Vues pour la gestion des entreprises clientes de la plateforme par le Super Admin."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.selectors.clients import (
    lister_clients_plateforme,
    obtenir_fiche_client,
)
from apps.platform_admin.serializers.clients import (
    ChangerPlanClientRequestSerializer,
    ClientPlateformeSerializer,
    SuspendreClientRequestSerializer,
)
from apps.platform_admin.serializers.impersonation import (
    ErreurPlateformeResponseSerializer,
)
from apps.platform_admin.services.clients import (
    changer_plan_client_plateforme,
    reactiver_client_plateforme,
    suspendre_client_plateforme,
)

__all__ = [
    "ChangerPlanClientPlateformeView",
    "ClientsPlateformeListView",
    "FicheClientPlateformeView",
    "ReactiverClientPlateformeView",
    "SuspendreClientPlateformeView",
]

PARAM_CLIENT_ID = OpenApiParameter(
    name="client_id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    description="Identifiant UUID de l'entreprise cliente.",
)


class ClientsPlateformeListView(APIView):
    """`GET /api/v1/clients/` — Liste complète des entreprises clientes de la plateforme."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = ClientPlateformeSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Liste des entreprises clientes de la plateforme",
        description=(
            "Renvoie la liste consolidée de toutes les entreprises clientes inscrites sur la "
            "plateforme, avec leur statut, leur forfait BTP en cours, leur date de création et "
            "leurs compteurs d'usage réels (nombre d'utilisateurs et nombre de chantiers actifs)."
        ),
        parameters=[
            OpenApiParameter(
                name="recherche",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtrer par raison sociale, nom commercial, slug ou email.",
            )
        ],
        responses={
            200: ClientPlateformeSerializer(many=True),
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
        },
    )
    def get(self, request):
        terme = request.query_params.get("recherche")
        donnees = lister_clients_plateforme(terme_recherche=terme)
        serializer = self.serializer_class(donnees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FicheClientPlateformeView(APIView):
    """`GET /api/v1/clients/{client_id}/` — Consultation détaillée de la fiche client."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = ClientPlateformeSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Détail complet d'une entreprise cliente (Fiche Client)",
        description=(
            "Renvoie les informations complètes d'une entreprise cliente : identité, "
            "coordonnées, état et historique de son abonnement, ainsi que ses compteurs d'usage "
            "réels (utilisateurs et chantiers)."
        ),
        parameters=[PARAM_CLIENT_ID],
        responses={
            200: ClientPlateformeSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
    )
    def get(self, request, client_id):
        donnees = obtenir_fiche_client(client_id)
        serializer = self.serializer_class(donnees)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SuspendreClientPlateformeView(APIView):
    """`POST /api/v1/clients/{client_id}/suspendre/` — Suspension d'un client par le Super Admin."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    @extend_schema(
        tags=["admins-clients"],
        summary="Suspendre une entreprise cliente",
        description=(
            "Suspend l'accès d'une entreprise cliente et de son abonnement. "
            "Exige la transmission d'un motif obligatoire. "
            "L'opération est tracée de façon immuable dans le Journal de Plateforme."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=SuspendreClientRequestSerializer,
        responses={
            200: ClientPlateformeSerializer,
            400: ErreurPlateformeResponseSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
            409: ErreurPlateformeResponseSerializer,
            422: ErreurPlateformeResponseSerializer,
        },
    )
    def post(self, request, client_id):
        serializer = SuspendreClientRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        motif = serializer.validated_data["motif"]
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        client_actualise = suspendre_client_plateforme(
            entreprise_id=client_id,
            motif=motif,
            admin_user=request.user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse_serializer = ClientPlateformeSerializer(client_actualise)
        return Response(reponse_serializer.data, status=status.HTTP_200_OK)


class ReactiverClientPlateformeView(APIView):
    """`POST /api/v1/clients/{client_id}/reactiver/` — Réactivation d'une entreprise cliente."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    @extend_schema(
        tags=["admins-clients"],
        summary="Réactiver une entreprise cliente suspendue",
        description=(
            "Rétablit l'accès et l'abonnement d'une entreprise précédemment suspendue. "
            "L'opération est tracée de façon immuable dans le Journal de Plateforme."
        ),
        parameters=[PARAM_CLIENT_ID],
        responses={
            200: ClientPlateformeSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
            409: ErreurPlateformeResponseSerializer,
        },
    )
    def post(self, request, client_id):
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        client_actualise = reactiver_client_plateforme(
            entreprise_id=client_id,
            admin_user=request.user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse_serializer = ClientPlateformeSerializer(client_actualise)
        return Response(reponse_serializer.data, status=status.HTTP_200_OK)


class ChangerPlanClientPlateformeView(APIView):
    """`PATCH /api/v1/clients/{client_id}/abonnement/` — Modification du forfait du client."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    @extend_schema(
        tags=["admins-clients"],
        summary="Modifier le forfait d'une entreprise cliente",
        description=(
            "Met à jour le plan d'abonnement d'une entreprise cliente ainsi que le tarif mensuel "
            "associé. L'opération est tracée de façon immuable dans le Journal de Plateforme."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=ChangerPlanClientRequestSerializer,
        responses={
            200: ClientPlateformeSerializer,
            400: ErreurPlateformeResponseSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
    )
    def patch(self, request, client_id):
        serializer = ChangerPlanClientRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_code = serializer.validated_data["plan_code"]
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        client_actualise = changer_plan_client_plateforme(
            entreprise_id=client_id,
            code_plan=plan_code,
            admin_user=request.user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse_serializer = ClientPlateformeSerializer(client_actualise)
        return Response(reponse_serializer.data, status=status.HTTP_200_OK)

    def post(self, request, client_id):
        """Permet l'appel en POST ou PATCH indifféremment."""
        return self.patch(request, client_id)
