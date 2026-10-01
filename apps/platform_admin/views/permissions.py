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
    AdminPermissionAffecterModulesSerializer,
    AdminPermissionCreateSerializer,
    AdminPermissionSerializer,
    AdminPermissionUpdateSerializer,
)
from apps.platform_admin.services.catalogue import (
    propager_affectation_modules_permission,
    propager_creation_permission,
    propager_modification_permission,
    propager_suppression_permission,
)

__all__ = [
    "AdminPermissionAffecterModulesView",
    "AdminPermissionDetailUpdateDeleteView",
    "AdminPermissionListCreateView",
]


class AdminPermissionListCreateView(APIView):
    """`GET` et `POST /api/v1/admin/permissions/` — Gestion du catalogue des autorisations par le Super Admin."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister toutes les permissions (Super Admin)",
        description="Renvoie le catalogue complet des autorisations configurées sur la plateforme avec leurs modules rattachés.",
        responses={200: AdminPermissionSerializer(many=True)},
    )
    def get(self, request):
        with schema_context("public"):
            permissions = (
                Permission.objects.filter(supprime_le__isnull=True)
                .prefetch_related("modules")
                .order_by("ordre", "code")
            )
            serializer = AdminPermissionSerializer(permissions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer une permission et propager à tous les tenants (Super Admin)",
        description="Crée une nouvelle permission granulaire et l'associe sélectivement aux modules spécifiés.",
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
                modules=serializer.validated_data.get("modules", []),
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
            perm = get_object_or_404(
                Permission.objects.prefetch_related("modules"), pk=pk, supprime_le__isnull=True
            )
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
                modules=serializer.validated_data.get("modules"),
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


class AdminPermissionAffecterModulesView(APIView):
    """`POST /api/v1/admin/permissions/{id}/modules/` — Décider et affecter les modules ayant accès à cette permission."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Affecter les modules autorisés à une permission (Super Admin)",
        description="Associe la permission exclusivement aux modules spécifiés, l'attribue aux rôles de direction sur ces modules et la révoque de tous les autres.",
        request=AdminPermissionAffecterModulesSerializer,
        responses={200: AdminPermissionSerializer},
    )
    def post(self, request, pk):
        serializer = AdminPermissionAffecterModulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            perm = propager_affectation_modules_permission(
                permission_id=pk,
                modules=serializer.validated_data["modules"],
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = AdminPermissionSerializer(perm)
        return Response(retour.data, status=status.HTTP_200_OK)
