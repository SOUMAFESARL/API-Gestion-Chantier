"""`/api/v1/admins/roles-systeme/` — les rôles système, gérés par le super admin."""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django_tenants.utils import schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models import ModeleRole, ModeleRoleModule
from apps.platform_admin.permissions import EstSuperAdminPlateforme, exiger_superviseur
from apps.platform_admin.serializers.roles_systeme import (
    RoleSystemeCreationSerializer,
    RoleSystemeModificationSerializer,
    RoleSystemeSerializer,
)
from apps.platform_admin.services.roles_systeme import (
    creer_role_systeme,
    modifier_role_systeme,
    supprimer_role_systeme,
)

__all__ = ["RoleSystemeDetailView", "RolesSystemeListeView"]


def _modeles():
    return ModeleRole.objects.prefetch_related(
        Prefetch("modules_plafonds", queryset=ModeleRoleModule.objects.all())
    ).order_by("code")


class RolesSystemeListeView(APIView):
    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(summary="Lister les rôles système", responses=RoleSystemeSerializer(many=True))
    def get(self, request):
        with schema_context("public"):
            return Response(RoleSystemeSerializer(_modeles(), many=True).data)

    @extend_schema(
        summary="Créer un rôle système et le propager à toutes les entreprises",
        request=RoleSystemeCreationSerializer,
        responses={201: RoleSystemeSerializer},
    )
    def post(self, request):
        exiger_superviseur(request)
        serializer = RoleSystemeCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        modele = creer_role_systeme(**serializer.validated_data, acteur=request.user)
        with schema_context("public"):
            retour = RoleSystemeSerializer(_modeles().get(pk=modele.pk)).data
        return Response(retour, status=status.HTTP_201_CREATED)


class RoleSystemeDetailView(APIView):
    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Modifier un rôle système",
        request=RoleSystemeModificationSerializer,
        responses=RoleSystemeSerializer,
    )
    def patch(self, request, pk):
        exiger_superviseur(request)
        with schema_context("public"):
            modele = get_object_or_404(ModeleRole, pk=pk)
        serializer = RoleSystemeModificationSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        modifier_role_systeme(modele, donnees=serializer.validated_data, acteur=request.user)
        with schema_context("public"):
            return Response(RoleSystemeSerializer(_modeles().get(pk=pk)).data)

    @extend_schema(summary="Supprimer un rôle système (il devient personnalisé partout)")
    def delete(self, request, pk):
        exiger_superviseur(request)
        with schema_context("public"):
            modele = get_object_or_404(ModeleRole, pk=pk)
        return Response(supprimer_role_systeme(modele, acteur=request.user))
