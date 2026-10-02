"""Vues d'authentification Super Admin — Plateforme CCD Digital."""

import logging

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import JetonsSerializer, RenouvellementSerializer
from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.serializers.auth import (
    ConnexionAdminSerializer,
    DeconnexionAdminResponseSerializer,
    DeconnexionAdminSerializer,
    ReponseConnexionAdminSerializer,
)
from apps.platform_admin.serializers.impersonation import (
    ErreurPlateformeResponseSerializer,
)
from apps.platform_admin.services.auth import (
    authentifier_super_admin,
    deconnecter_super_admin,
    renouveler_super_admin,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConnexionAdminView",
    "DeconnexionAdminView",
    "RenouvellementAdminView",
]


class ConnexionAdminView(APIView):
    """Connexion Super Admin — `POST /api/v1/admins/connexion/`.

    Authentifie un Super Administrateur de la plateforme par son email et son
    mot de passe. Vérifie que le compte vit dans le schéma public et possède
    `is_superuser=True`. Ne requiert aucune restriction d'adresse IP.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]

    @extend_schema(
        tags=["admins"],
        summary="Connexion Super Admin",
        description=(
            "Point d'entrée d'authentification dédié au Super Administrateur de la plateforme. "
            "Seuls les comptes ayant `is_superuser=True` dans le schéma public sont autorisés. "
            "L'accès est accordé sur présentation exclusive de l'email et du mot de passe valides."
        ),
        request=ConnexionAdminSerializer,
        responses={
            200: ReponseConnexionAdminSerializer,
            401: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Succès de connexion Super Admin",
                value={
                    "access": "eyJhbGciOi...",
                    "refresh": "eyJhbGciOi...",
                    "expire_dans": 900,
                    "utilisateur": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        "email": "superadmin@ccd-digital.ci",
                        "nom": "Super",
                        "prenom": "Admin",
                        "role_global": "ADMIN",
                        "role_libelle": "Administrateur",
                        "is_superuser": True,
                        "is_staff": True,
                        "langue": "fr",
                        "schema": "public",
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Identifiants invalides ou non superuser",
                value={
                    "erreur": {
                        "code": "identifiants_invalides",
                        "message": "Email ou mot de passe incorrect.",
                        "details": {},
                        "trace_id": "1929460ac2b249bfa69625880768c730",
                    }
                },
                response_only=True,
                status_codes=["401"],
            ),
        ],
    )
    def post(self, request):
        serializer = ConnexionAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]
        origine = serializer.validated_data.get("origine", "WEB")

        resultat = authentifier_super_admin(
            email=serializer.validated_data["email"],
            mot_de_passe=serializer.validated_data["mot_de_passe"],
            adresse_ip=adresse_ip,
            appareil=appareil,
            origine=origine,
        )

        reponse = Response(resultat, status=status.HTTP_200_OK)
        reponse["Cache-Control"] = "no-store"
        return reponse


class DeconnexionAdminView(APIView):
    """Déconnexion Super Admin — `POST /api/v1/admins/deconnexion/`.

    Clôture la session Super Admin, révoque le jeton de renouvellement côté serveur
    dans Redis et journalise l'événement dans le journal de plateforme.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]

    @extend_schema(
        tags=["admins"],
        summary="Déconnexion Super Admin",
        description="Termine la session Super Admin et révoque le jeton de renouvellement.",
        request=DeconnexionAdminSerializer,
        responses={200: DeconnexionAdminResponseSerializer},
    )
    def post(self, request):
        serializer = DeconnexionAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh = serializer.validated_data.get("refresh")
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        deconnecter_super_admin(
            refresh_token=refresh,
            utilisateur=getattr(request, "user", None),
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse = Response({"message": _("Déconnexion réussie.")}, status=status.HTTP_200_OK)
        reponse["Cache-Control"] = "no-store"
        return reponse


class RenouvellementAdminView(APIView):
    """Renouvellement jeton Super Admin — `POST /api/v1/admins/token/refresh/`."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]

    @extend_schema(
        tags=["admins"],
        summary="Renouvellement jeton Super Admin",
        description="Renouvelle la paire de jetons d'accès Super Admin avec rotation.",
        request=RenouvellementSerializer,
        responses={200: JetonsSerializer},
    )
    def post(self, request):
        serializer = RenouvellementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resultat = renouveler_super_admin(serializer.validated_data["refresh"])

        reponse = Response(resultat, status=status.HTTP_200_OK)
        reponse["Cache-Control"] = "no-store"
        return reponse
