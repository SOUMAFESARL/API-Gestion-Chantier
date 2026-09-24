"""Vues de réinitialisation de mot de passe Super Admin — Control Plane CCD Digital."""

import logging

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.throttling import (
    ThrottleDemandeMdpParEmail,
    ThrottleDemandeMdpRapprochee,
)
from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.serializers.auth import (
    ContenuJetonAdminSerializer,
    DemandeReinitialisationAdminSerializer,
    ReinitialisationAdminSerializer,
    ReponseDemandeReinitialisationAdminSerializer,
    ReponseReinitialisationAdminSerializer,
    VerificationJetonAdminSerializer,
)
from apps.platform_admin.serializers.impersonation import (
    ErreurPlateformeResponseSerializer,
)
from apps.platform_admin.services.reinitialisation import (
    demander_reinitialisation_super_admin,
    reinitialiser_mot_de_passe_super_admin,
    verifier_jeton_super_admin,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DemandeReinitialisationAdminView",
    "ReinitialisationAdminView",
    "VerificationJetonAdminView",
]


class DemandeReinitialisationAdminView(APIView):
    """Demande de réinitialisation Super Admin — `POST /api/v1/admins/mot-de-passe/demande/`.

    **Répond toujours 202 Accepted**, que l'adresse existe ou non et qu'elle appartienne
    à un Super Admin ou non, pour interdire toute énumération d'adresses.
    L'email de réinitialisation n'est envoyé qu'aux comptes du schéma `public`
    ayant `is_superuser=True`.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [
        ScopedRateThrottle,
        ThrottleDemandeMdpParEmail,
        ThrottleDemandeMdpRapprochee,
    ]
    throttle_scope = "mdp_demande"

    @extend_schema(
        tags=["admins"],
        summary="Demander un lien de réinitialisation Super Admin",
        description=(
            "Initie une demande de réinitialisation de mot de passe pour le Super Administrateur. "
            "Répond systématiquement avec un statut HTTP 202 Accepted sans divulguer l'existence "
            "du compte."
        ),
        request=DemandeReinitialisationAdminSerializer,
        responses={
            202: ReponseDemandeReinitialisationAdminSerializer,
            400: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Succès silencieux (202 Accepted)",
                value={
                    "message": (
                        "Si cette adresse correspond à un compte administrateur, "
                        "un email vient d'être envoyé."
                    ),
                    "expire_dans": 3600,
                },
                response_only=True,
                status_codes=["202"],
            )
        ],
    )
    def post(self, request):
        serializer = DemandeReinitialisationAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        resultat = demander_reinitialisation_super_admin(
            email=serializer.validated_data["email"],
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        return Response(resultat, status=status.HTTP_202_ACCEPTED)


class VerificationJetonAdminView(APIView):
    """Vérification de jeton Super Admin — `POST /api/v1/admins/mot-de-passe/verifier/`.

    **Le jeton est inspecté sans être consommé** (règle R-32).
    Renvoie 200 OK si le jeton est valide, ou 410 Gone s'il est expiré ou inexistant.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mdp_verifier"

    @extend_schema(
        tags=["admins"],
        summary="Vérifier un jeton de réinitialisation Super Admin",
        description="Vérifie la validité d'un jeton Super Admin sans le consommer.",
        request=VerificationJetonAdminSerializer,
        responses={
            200: ContenuJetonAdminSerializer,
            410: ErreurPlateformeResponseSerializer,
        },
    )
    def post(self, request):
        serializer = VerificationJetonAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        jeton = verifier_jeton_super_admin(serializer.validated_data["jeton"])
        reste = int((jeton.expire_le - timezone.now()).total_seconds())

        base_frontend = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        url_connexion = f"{base_frontend}/admin/connexion"

        return Response(
            {
                "email": jeton.utilisateur.email,
                "motif": jeton.motif,
                "expire_dans": max(0, reste),
                "url_connexion": url_connexion,
            },
            status=status.HTTP_200_OK,
        )


class ReinitialisationAdminView(APIView):
    """Réinitialisation de mot de passe Super Admin.

    `POST /api/v1/admins/mot-de-passe/reinitialiser/`.
    Applique le nouveau mot de passe, consomme le jeton, journalise l'audit et révoque
    toutes les sessions actives.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mdp_reinitialiser"

    @extend_schema(
        tags=["admins"],
        summary="Enregistrer un nouveau mot de passe Super Admin",
        description=(
            "Consomme le jeton de réinitialisation, applique le nouveau mot de passe Super Admin "
            "et révoque immédiatement toutes les sessions existantes."
        ),
        request=ReinitialisationAdminSerializer,
        responses={
            200: ReponseReinitialisationAdminSerializer,
            400: ErreurPlateformeResponseSerializer,
            410: ErreurPlateformeResponseSerializer,
        },
    )
    def post(self, request):
        serializer = ReinitialisationAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        reinitialiser_mot_de_passe_super_admin(
            jeton_clair=serializer.validated_data["jeton"],
            mot_de_passe=serializer.validated_data["mot_de_passe"],
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        return Response(
            {
                "message": _(
                    "Votre mot de passe administrateur a été enregistré avec succès. "
                    "Toutes vos sessions actives ont été fermées."
                )
            },
            status=status.HTTP_200_OK,
        )
