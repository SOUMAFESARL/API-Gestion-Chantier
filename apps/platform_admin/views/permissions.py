"""Vues API pour la gestion dynamique des autorisations par le Super Admin."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Permission
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.serializers.permissions import (
    AdminPermissionCreateSerializer,
    AdminPermissionSerializer,
    AdminPermissionUpdateSerializer,
)
from apps.platform_admin.services.catalogue import (
    propager_creation_permission,
    propager_modification_permission,
    propager_suppression_permission,
)

__all__ = [
    "AdminPermissionDetailUpdateDeleteView",
    "AdminPermissionListCreateView",
]


class AdminPermissionListCreateView(APIView):
    """`GET` et `POST /api/v1/admin/permissions/` — Gestion du catalogue des autorisations par le Super Admin."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister toutes les permissions (Super Admin)",
        description="Renvoie le catalogue complet des autorisations configurées sur la plateforme.",
        responses={200: AdminPermissionSerializer(many=True)},
    )
    def get(self, request):
        with schema_context("public"):
            permissions = Permission.objects.filter(supprime_le__isnull=True).order_by("ordre", "code")
            serializer = AdminPermissionSerializer(permissions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer une permission et propager à tous les tenants (Super Admin)",
        description="Crée une nouvelle permission granulaire et l'associe automatiquement aux rôles de direction dans chaque tenant.",
        request=AdminPermissionCreateSerializer,
        responses={201: AdminPermissionSerializer},
    )
    def post(self, request):
        with schema_context("public"):
            serializer = AdminPermissionCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

        try:
            perm = propager_creation_permission(
                code=serializer.validated_data["code"],
                libelle=serializer.validated_data["libelle"],
                description=serializer.validated_data.get("description", ""),
                ordre=serializer.validated_data.get("ordre", 0),
                est_actif=serializer.validated_data.get("est_actif", True),
                cree_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = AdminPermissionSerializer(perm)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class AdminPermissionDetailUpdateDeleteView(APIView):
    """`GET`, `PATCH` et `DELETE /api/v1/admin/permissions/{id}/` — Détail, modification et suppression d'une permission."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'une permission (Super Admin)",
        responses={200: AdminPermissionSerializer},
    )
    def get(self, request, pk):
        with schema_context("public"):
            perm = get_object_or_404(Permission, pk=pk, supprime_le__isnull=True)
            serializer = AdminPermissionSerializer(perm)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier une permission et propager (Super Admin)",
        request=AdminPermissionUpdateSerializer,
        responses={200: AdminPermissionSerializer},
    )
    def patch(self, request, pk):
        serializer = AdminPermissionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            perm_maj = propager_modification_permission(
                permission_id=pk,
                libelle=serializer.validated_data.get("libelle"),
                description=serializer.validated_data.get("description"),
                ordre=serializer.validated_data.get("ordre"),
                est_actif=serializer.validated_data.get("est_actif"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = AdminPermissionSerializer(perm_maj)
        return Response(retour.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer logiquement une permission (Super Admin)",
        responses={200: dict},
    )
    def delete(self, request, pk):
        try:
            resultat = propager_suppression_permission(
                permission_id=pk,
                supprime_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(
            {
                "message": _("Permission supprimée avec succès."),
                **resultat,
            },
            status=status.HTTP_200_OK,
        )
