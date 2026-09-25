"""Vues API pour la ressource profil utilisateur (/api/v1/auth/profil/)."""

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers.profil import (
    AvatarReponseSerializer,
    AvatarUploadSerializer,
    ChangerMotDePasseReponseSerializer,
    ChangerMotDePasseSerializer,
    ProfilDetailResponseSerializer,
    ProfilUpdateSerializer,
)
from apps.accounts.services.profil import (
    changer_mot_de_passe,
    enregistrer_avatar,
    mettre_a_jour_profil,
    obtenir_donnees_profil,
    supprimer_avatar,
)

__all__ = [
    "AvatarProfilView",
    "ChangerMotDePasseView",
    "ProfilView",
]


class ProfilView(APIView):
    """Consultation et modification partielle du profil de l'utilisateur connecté."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Consulter mon profil",
        responses={200: ProfilDetailResponseSerializer},
    )
    def get(self, request):
        donnees = obtenir_donnees_profil(request.user, request=request)
        return Response(donnees, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Mettre à jour mon profil",
        request=ProfilUpdateSerializer,
        responses={200: ProfilDetailResponseSerializer},
    )
    def patch(self, request):
        serializer = ProfilUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        mettre_a_jour_profil(
            request.user,
            serializer.validated_data,
            ip=request.META.get("REMOTE_ADDR"),
            appareil=request.META.get("HTTP_USER_AGENT", "")[:255],
        )

        donnees = obtenir_donnees_profil(request.user, request=request)
        return Response(donnees, status=status.HTTP_200_OK)


class ChangerMotDePasseView(APIView):
    """Modification autonome du mot de passe pour l'utilisateur connecté."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Changer mon mot de passe",
        request=ChangerMotDePasseSerializer,
        responses={200: ChangerMotDePasseReponseSerializer},
    )
    def post(self, request):
        serializer = ChangerMotDePasseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resultat = changer_mot_de_passe(
            request.user,
            ancien_mot_de_passe=serializer.validated_data["ancien_mot_de_passe"],
            nouveau_mot_de_passe=serializer.validated_data["nouveau_mot_de_passe"],
            ip=request.META.get("REMOTE_ADDR"),
            appareil=request.META.get("HTTP_USER_AGENT", "")[:255],
            origine=serializer.validated_data.get("origine", "WEB"),
        )

        reponse = Response(resultat, status=status.HTTP_200_OK)
        reponse["Cache-Control"] = "no-store"
        return reponse


class AvatarProfilView(APIView):
    """Téléversement et suppression de la photo de profil (avatar)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Téléverser une photo de profil",
        request=AvatarUploadSerializer,
        responses={200: AvatarReponseSerializer},
    )
    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fichier = serializer.validated_data["avatar"]
        avatar_url = enregistrer_avatar(request.user, fichier, request=request)

        return Response(
            {
                "avatar_url": avatar_url,
                "message": _("Photo de profil mise à jour avec succès."),
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Supprimer la photo de profil",
        responses={200: AvatarReponseSerializer},
    )
    def delete(self, request):
        supprimer_avatar(request.user)
        return Response(
            {
                "avatar_url": None,
                "message": _("Photo de profil supprimée avec succès."),
            },
            status=status.HTTP_200_OK,
        )
