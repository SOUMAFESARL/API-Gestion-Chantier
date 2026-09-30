"""Vues API pour la gestion dynamique des modules par le Super Admin."""

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

from apps.accounts.models import Module
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.serializers.modules import (
    AdminModuleCreateSerializer,
    AdminModuleDetailSerializer,
    AdminModuleListSerializer,
    AdminModuleUpdateSerializer,
)
from apps.platform_admin.services.catalogue import (
    propager_creation_module,
    propager_modification_module,
    propager_suppression_module,
)

__all__ = [
    "AdminModuleDetailUpdateDeleteView",
    "AdminModuleListCreateView",
]


class AdminModuleListCreateView(APIView):
    """`GET` et `POST /api/v1/admin/modules/` — Gestion du catalogue des modules par le Super Admin."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister tous les modules (Super Admin)",
        description="Renvoie l'ensemble des modules configurés sur la plateforme.",
        responses={200: AdminModuleListSerializer(many=True)},
    )
    def get(self, request):
        with schema_context("public"):
            modules = Module.objects.filter(supprime_le__isnull=True).order_by("ordre", "code")
            serializer = AdminModuleListSerializer(modules, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un module et propager à tous les tenants (Super Admin)",
        description="Crée un nouveau module applicatif et l'attache automatiquement à tous les rôles de toutes les entreprises clientes.",
        request=AdminModuleCreateSerializer,
        responses={201: AdminModuleDetailSerializer},
    )
    def post(self, request):
        with schema_context("public"):
            serializer = AdminModuleCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

        try:
            module = propager_creation_module(
                code=serializer.validated_data["code"],
                libelle=serializer.validated_data["libelle"],
                description=serializer.validated_data.get("description", ""),
                ordre=serializer.validated_data.get("ordre", 0),
                icone=serializer.validated_data.get("icone", "box"),
                est_actif=serializer.validated_data.get("est_actif", True),
                cree_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = AdminModuleDetailSerializer(module)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class AdminModuleDetailUpdateDeleteView(APIView):
    """`GET`, `PATCH` et `DELETE /api/v1/admin/modules/{id}/` — Détail, modification et suppression d'un module."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'un module (Super Admin)",
        responses={200: AdminModuleDetailSerializer},
    )
    def get(self, request, pk):
        with schema_context("public"):
            module = get_object_or_404(Module, pk=pk, supprime_le__isnull=True)
            serializer = AdminModuleDetailSerializer(module)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un module et propager (Super Admin)",
        request=AdminModuleUpdateSerializer,
        responses={200: AdminModuleDetailSerializer},
    )
    def patch(self, request, pk):
        serializer = AdminModuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            module_maj = propager_modification_module(
                module_id=pk,
                libelle=serializer.validated_data.get("libelle"),
                description=serializer.validated_data.get("description"),
                ordre=serializer.validated_data.get("ordre"),
                icone=serializer.validated_data.get("icone"),
                est_actif=serializer.validated_data.get("est_actif"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = AdminModuleDetailSerializer(module_maj)
        return Response(retour.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer logiquement un module (Super Admin)",
        responses={200: dict},
    )
    def delete(self, request, pk):
        try:
            resultat = propager_suppression_module(
                module_id=pk,
                supprime_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(
            {
                "message": _("Module supprimé avec succès."),
                **resultat,
            },
            status=status.HTTP_200_OK,
        )
