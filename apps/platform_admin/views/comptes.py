"""Vues pour la gestion des comptes administrateurs et du profil de l'agent connecté (Super Admin)."""

import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.serializers.comptes import (
    CompteAdministrateurSerializer,
    CreerCompteAdministrateurSerializer,
    ModifierProfilAdminSerializer,
    ProfilCompletAdminSerializer,
)

__all__ = [
    "AdminChangerMotDePasseMoiView",
    "AdminPhotoMoiView",
    "AdminProfilMoiView",
    "ComptesAdministrateursListCreateView",
    "ReactiverCompteAdministrateurView",
    "SuspendreCompteAdministrateurView",
]


class ComptesAdministrateursListCreateView(APIView):
    """`GET` et `POST /api/v1/admins/comptes/` — Liste et création des agents du back-office."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les comptes agents (Super Admin)",
        description="Renvoie la liste des comptes d'administration de la plateforme dans le schéma public.",
        responses={200: CompteAdministrateurSerializer(many=True)},
    )
    def get(self, request):
        with schema_context("public"):
            comptes = Utilisateur.objects.filter(
                supprime_le__isnull=True,
            ).order_by("-cree_le")
            serializer = CompteAdministrateurSerializer(comptes, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer ou inviter un agent (Super Admin)",
        description="Crée un nouveau compte administrateur dans le schéma public.",
        request=CreerCompteAdministrateurSerializer,
        responses={201: CompteAdministrateurSerializer},
    )
    def post(self, request):
        serializer = CreerCompteAdministrateurSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        role = data.get("role", "SUPPORT")
        is_super = (role == "SUPERVISEUR")

        with schema_context("public"):
            # Mot de passe temporaire aléatoire
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            mot_de_passe_temp = "".join(secrets.choice(alphabet) for _ in range(16))

            nouvel_agent = Utilisateur(
                email=data["email"],
                nom=data["nom"],
                prenom=data["prenom"],
                role_global=RoleGlobal.ADMIN,
                is_superuser=is_super,
                is_staff=True,
                is_active=True,
                statut=StatutUtilisateur.ACTIF,
            )
            nouvel_agent.set_password(mot_de_passe_temp)
            nouvel_agent.save()

            retour = CompteAdministrateurSerializer(nouvel_agent)
            return Response(retour.data, status=status.HTTP_201_CREATED)


class SuspendreCompteAdministrateurView(APIView):
    """`POST /api/v1/admins/comptes/{id}/suspendre/` — Suspendre un compte administrateur."""

    permission_classes = [EstSuperAdminPlateforme]

    @extend_schema(
        summary="Suspendre un compte agent (Super Admin)",
        request=None,
        responses={200: CompteAdministrateurSerializer},
    )
    def post(self, request, pk):
        with schema_context("public"):
            agent = get_object_or_404(Utilisateur, pk=pk, supprime_le__isnull=True)
            if str(agent.id) == str(request.user.id):
                return Response(
                    {"erreur": {"code": "interdiction", "message": _("Vous ne pouvez pas suspendre votre propre compte.")}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            agent.is_active = False
            agent.statut = StatutUtilisateur.DESACTIVE
            agent.save(update_fields=["is_active", "statut", "modifie_le"])

            return Response(CompteAdministrateurSerializer(agent).data, status=status.HTTP_200_OK)


class ReactiverCompteAdministrateurView(APIView):
    """`POST /api/v1/admins/comptes/{id}/reactiver/` — Réactiver un compte administrateur."""

    permission_classes = [EstSuperAdminPlateforme]

    @extend_schema(
        summary="Réactiver un compte agent (Super Admin)",
        request=None,
        responses={200: CompteAdministrateurSerializer},
    )
    def post(self, request, pk):
        with schema_context("public"):
            agent = get_object_or_404(Utilisateur, pk=pk, supprime_le__isnull=True)
            agent.is_active = True
            agent.statut = StatutUtilisateur.ACTIF
            agent.save(update_fields=["is_active", "statut", "modifie_le"])

            return Response(CompteAdministrateurSerializer(agent).data, status=status.HTTP_200_OK)


class AdminProfilMoiView(APIView):
    """`GET` et `PATCH /api/v1/admins/moi/` — Consultation et mise à jour du profil de l'agent connecté."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Profil de l'administrateur connecté",
        responses={200: ProfilCompletAdminSerializer},
    )
    def get(self, request):
        with schema_context("public"):
            user = get_object_or_404(Utilisateur, pk=request.user.pk, supprime_le__isnull=True)
            return Response(ProfilCompletAdminSerializer(user).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier son profil administrateur",
        request=ModifierProfilAdminSerializer,
        responses={200: ProfilCompletAdminSerializer},
    )
    def patch(self, request):
        serializer = ModifierProfilAdminSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)

        with schema_context("public"):
            user = get_object_or_404(Utilisateur, pk=request.user.pk, supprime_le__isnull=True)
            data = serializer.validated_data
            if "prenom" in data:
                user.prenom = data["prenom"]
            if "nom" in data:
                user.nom = data["nom"]
            if "email" in data:
                user.email = data["email"]
            if "telephone" in data:
                user.telephone = data["telephone"]
            user.save()

            return Response(ProfilCompletAdminSerializer(user).data, status=status.HTTP_200_OK)


class AdminPhotoMoiView(APIView):
    """`PATCH /api/v1/admins/moi/photo/` — Mettre à jour ou supprimer la photo de profil."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Modifier ou supprimer sa photo de profil",
        request=inline_serializer(name="AdminPhotoRequest", fields={
            "photo": serializers.ImageField(required=False),
            "retirer_photo": serializers.BooleanField(required=False),
        }),
        responses={200: ProfilCompletAdminSerializer},
    )
    def patch(self, request):
        with schema_context("public"):
            user = get_object_or_404(Utilisateur, pk=request.user.pk, supprime_le__isnull=True)
            if request.data.get("retirer_photo") in ["true", True, "1"]:
                if user.avatar:
                    user.avatar.delete(save=False)
                    user.avatar = None
            elif "photo" in request.FILES:
                user.avatar = request.FILES["photo"]
            user.save()

            return Response(ProfilCompletAdminSerializer(user).data, status=status.HTTP_200_OK)


class AdminChangerMotDePasseMoiView(APIView):
    """`POST /api/v1/admins/moi/mot-de-passe/` — Changer son mot de passe administrateur."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Changer son mot de passe (Super Admin)",
        request=inline_serializer(name="AdminMotDePasseRequest", fields={
            "ancien_mot_de_passe": serializers.CharField(write_only=True),
            "nouveau_mot_de_passe": serializers.CharField(write_only=True),
        }),
        responses={200: dict, 400: dict},
    )
    def post(self, request):
        ancien = request.data.get("ancien_mot_de_passe", "")
        nouveau = request.data.get("nouveau_mot_de_passe", "")

        if not ancien:
            raise ValidationError({"ancien_mot_de_passe": [_("L'ancien mot de passe est obligatoire.")]})
        if not nouveau:
            raise ValidationError({"nouveau_mot_de_passe": [_("Le nouveau mot de passe est obligatoire.")]})

        with schema_context("public"):
            user = get_object_or_404(Utilisateur, pk=request.user.pk, supprime_le__isnull=True)
            if not user.check_password(ancien):
                raise ValidationError({"ancien_mot_de_passe": [_("Ancien mot de passe incorrect.")]})

            try:
                validate_password(nouveau, user=user)
            except DjangoValidationError as exc:
                raise ValidationError({"nouveau_mot_de_passe": list(exc.messages)})

            user.set_password(nouveau)
            user.save()

            return Response({"message": _("Mot de passe modifié avec succès.")}, status=status.HTTP_200_OK)
