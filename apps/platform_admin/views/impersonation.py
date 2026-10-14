"""Vues pour l'assistance Super Admin et la consultation du journal plateforme."""

import logging

from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Utilisateur
from apps.core.ip_restriction import extraire_ip_client
from apps.core.pagination import PaginationStandard
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.selectors import codes_actions_journal, journal_plateforme
from apps.platform_admin.serializers.impersonation import (
    DeconnexionAssistanceRequestSerializer,
    DeconnexionAssistanceResponseSerializer,
    DemandeAssistanceSerializer,
    ErreurPlateformeResponseSerializer,
    FiltresJournalPlateformeSerializer,
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
from apps.tenants.models import Entreprise

logger = logging.getLogger(__name__)

__all__ = [
    "ActionsJournalPlateformeView",
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
            if not entreprise_id and payload.get("schema"):
                from apps.tenants.models import Entreprise
                ent = Entreprise.objects.filter(schema_name=payload.get("schema")).first()
                if ent:
                    entreprise_id = ent.id

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

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    @extend_schema(
        tags=["admins"],
        summary="Consulter le journal d'audit plateforme",
        description=(
            "Consulte le journal d'audit de la plateforme filtré par période, agent, entreprise "
            "ou action, paginé (20 par page par défaut, 100 max)."
        ),
        parameters=[
            OpenApiParameter(
                name="du",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Date de début incluse (format AAAA-MM-JJ).",
                required=False,
            ),
            OpenApiParameter(
                name="au",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Date de fin incluse (format AAAA-MM-JJ).",
                required=False,
            ),
            OpenApiParameter(
                name="utilisateur_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filtrer les événements par identifiant de l'agent.",
                required=False,
            ),
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
                description="Filtrer par code d'action exact.",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Numéro de page.",
                required=False,
            ),
            OpenApiParameter(
                name="taille_page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Nombre d'éléments par page (max 100).",
                required=False,
            ),
        ],
        responses={
            200: PaginationStandard().get_paginated_response_schema(
                JournalPlateformeSerializer(many=True).data
            ),
            400: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
        },
    )
    def get(self, request):
        verifier_super_admin(request.user)
        filtres = FiltresJournalPlateformeSerializer(data=request.query_params)
        filtres.is_valid(raise_exception=True)

        with schema_context(get_public_schema_name()):
            qs = journal_plateforme(**filtres.validated_data)
            pagination = PaginationStandard()
            page = pagination.paginate_queryset(qs, request, view=self)

            ids_agents = {e.utilisateur_id for e in page if e.utilisateur_id}
            ids_entreprises = {e.entreprise_id for e in page if e.entreprise_id}
            noms_agents = {
                str(u.id): (f"{u.prenom} {u.nom}".strip() or u.email)
                for u in Utilisateur.tous_objets.filter(id__in=ids_agents).only(
                    "id", "prenom", "nom", "email"
                )
            }
            noms_entreprises = {
                str(e.id): (e.nom_commercial or e.raison_sociale)
                for e in Entreprise.objects.filter(id__in=ids_entreprises).only(
                    "id", "nom_commercial", "raison_sociale"
                )
            }

            contexte = {
                "noms_agents": noms_agents,
                "noms_entreprises": noms_entreprises,
            }
            donnees = JournalPlateformeSerializer(page, many=True, context=contexte).data
            return pagination.get_paginated_response(donnees)


class ActionsJournalPlateformeView(APIView):
    """`GET /api/v1/admins/journal-plateforme/actions/` — les codes d'action présents au journal."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    @extend_schema(
        tags=["admins"],
        summary="Lister les codes d'action du journal plateforme",
        description="Retourne la liste triée des codes d'action distincts présents au journal.",
        responses={
            200: OpenApiTypes.OBJECT,
            403: ErreurPlateformeResponseSerializer,
        },
    )
    def get(self, request):
        verifier_super_admin(request.user)
        with schema_context(get_public_schema_name()):
            return Response(
                {"actions": codes_actions_journal()},
                status=status.HTTP_200_OK,
            )
