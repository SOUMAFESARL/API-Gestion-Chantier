"""Vues pour l'assistance Super Admin et la consultation du journal plateforme."""

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.serializers.impersonation import (
    DeconnexionAssistanceRequestSerializer,
    DeconnexionAssistanceResponseSerializer,
    DemandeAssistanceSerializer,
    ErreurPlateformeResponseSerializer,
    JournalPlateformeSerializer,
    ReponseAssistanceSerializer,
    UtilisateurCibleSerializer,
)
from apps.platform_admin.services.impersonation import (
    clore_session_assistance,
    demarrer_session_assistance,
    lister_utilisateurs_entreprise,
    verifier_super_admin,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DeconnexionAssistanceView",
    "DemarrerAssistanceView",
    "JournalPlateformeListView",
    "ListerUtilisateursEntrepriseView",
]


class DemarrerAssistanceView(APIView):
    """Démarre une session d'assistance Super Admin (lecture seule, session 1h)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["admins"],
        summary="Démarrer une session d'assistance Super Admin",
        description=(
            "Permet à un Super Administrateur d'accéder au compte d'une entreprise "
            "cliente en direct pour l'assister en lecture seule (durée 1h stricte, double traçabilité d'audit). "
            "Règle R-128 : Toute tentative de modification ultérieure sera rejetée par le middleware."
        ),
        parameters=[
            OpenApiParameter(
                name="entreprise_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Identifiant UUID de l'entreprise cliente à assister.",
            )
        ],
        request=DemandeAssistanceSerializer,
        responses={
            200: ReponseAssistanceSerializer,
            400: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
    )
    def post(self, request, entreprise_id):
        serializer = DemandeAssistanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        motif = serializer.validated_data["motif"]
        utilisateur_id = serializer.validated_data.get("utilisateur_id")
        ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")

        resultat = demarrer_session_assistance(
            super_admin=request.user,
            entreprise_id=entreprise_id,
            motif=motif,
            utilisateur_id=utilisateur_id,
            adresse_ip=ip,
            appareil=appareil,
        )

        return Response(resultat, status=status.HTTP_200_OK)


class DeconnexionAssistanceView(APIView):
    """Clôture la session d'assistance Super Admin et enregistre la fin de session."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["admins"],
        summary="Clôturer une session d'assistance Super Admin",
        description="Termine la session d'assistance Super Admin et consigne la déconnexion dans les journaux d'audit.",
        request=DeconnexionAssistanceRequestSerializer,
        responses={
            200: DeconnexionAssistanceResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
        },
    )
    def post(self, request):
        ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")

        super_admin_id = None
        super_admin_email = ""
        entreprise_id = request.data.get("entreprise_id")

        if hasattr(request, "impersonation_payload") and request.impersonation_payload:
            payload = request.impersonation_payload
            super_admin_id = payload.get("impersonateur_id")
            super_admin_email = payload.get("impersonateur_email", "")

        clore_session_assistance(
            super_admin_id=super_admin_id,
            super_admin_email=super_admin_email,
            entreprise_id=entreprise_id,
            adresse_ip=ip,
            appareil=appareil,
        )

        return Response(
            {"statut": "deconnecte", "message": "Session d'assistance clôturée avec succès."},
            status=status.HTTP_200_OK,
        )


class ListerUtilisateursEntrepriseView(APIView):
    """Liste les utilisateurs d'une entreprise pour cibler l'assistance."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["admins"],
        summary="Lister les utilisateurs d'une entreprise pour assistance",
        description="Liste l'ensemble des collaborateurs d'une entreprise cliente afin de permettre au Super Admin de cibler un profil spécifique pour la session d'assistance.",
        parameters=[
            OpenApiParameter(
                name="entreprise_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Identifiant UUID de l'entreprise cliente.",
            )
        ],
        responses={
            200: UtilisateurCibleSerializer(many=True),
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
    )
    def get(self, request, entreprise_id):
        verifier_super_admin(request.user)
        utilisateurs = lister_utilisateurs_entreprise(entreprise_id)
        serializer = UtilisateurCibleSerializer(utilisateurs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class JournalPlateformeListView(APIView):
    """Consultation du journal d'audit de la plateforme (MLD §4.6)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["admins"],
        summary="Consulter le journal d'audit plateforme",
        description="Consulte les 200 derniers événements immuables de support et d'administration enregistrés sur la plateforme (MLD §4.6).",
        parameters=[
            OpenApiParameter(
                name="entreprise_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filtrer les événements par identifiant de l'entreprise cliente.",
                required=False,
            ),
            OpenApiParameter(
                name="action",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filtrer par code d'action (ex: CONNEXION_ASSISTANCE, DECONNEXION_ASSISTANCE, TENTATIVE_ECRITURE_BLOQUEE).",
                required=False,
            ),
        ],
        responses={
            200: JournalPlateformeSerializer(many=True),
            403: ErreurPlateformeResponseSerializer,
        },
    )
    def get(self, request):
        verifier_super_admin(request.user)

        qs = JournalPlateforme.objects.all().order_by("-horodatage")

        entreprise_id = request.query_params.get("entreprise_id")
        if entreprise_id:
            qs = qs.filter(entreprise_id=entreprise_id)

        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)

        # Limitation à 200 entrées les plus récentes pour l'affichage réactif
        qs = qs[:200]
        serializer = JournalPlateformeSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
