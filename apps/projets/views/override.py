"""Vues pour la gestion des surcharges de permissions par projet (Approche Hybride)."""

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.enums import RoleGlobal
from apps.projets.models import Projet
from apps.projets.services.overrides import (
    get_matrice_permissions_projet,
    set_override_permission_projet,
    supprimer_override_permission_projet,
)

__all__ = ["ProjetPermissionsRolesView"]


class OverrideInputSerializer(serializers.Serializer):
    role_id = serializers.UUIDField()
    module = serializers.CharField()
    niveau = serializers.IntegerField(min_value=0, max_value=3, required=False, allow_null=True)


class SurchargeMatriceInputSerializer(serializers.Serializer):
    surcharges = OverrideInputSerializer(many=True, required=False, default=list)


class ProjetPermissionsRolesView(APIView):
    """`GET` et `PUT /api/v1/projets/{id}/permissions-roles/` — Matrice des droits par chantier."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Matrice des rôles et habilitations effectives sur ce chantier",
        responses={200: list},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk, supprime_le__isnull=True)
        matrice = get_matrice_permissions_projet(projet)
        return Response(matrice, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Appliquer des surcharges de droits sur ce chantier",
        request=SurchargeMatriceInputSerializer,
        responses={200: list},
    )
    def put(self, request, pk):
        # Seul l'administrateur ou le chef de projet assigné peut modifier les droits du chantier
        projet = get_object_or_404(Projet, pk=pk, supprime_le__isnull=True)

        est_admin = request.user.role_global in (
            RoleGlobal.ADMIN,
            RoleGlobal.DIRECTEUR_GENERAL,
        ) or getattr(request.user, "is_owner", False)
        est_chef_projet = (
            projet.chef_projet_id == request.user.id
            or request.user.role_global == RoleGlobal.CHEF_PROJET
        )

        if not (est_admin or est_chef_projet):
            return Response(
                {
                    "detail": _(
                        "Vous n'avez pas les droits pour modifier les habilitations de ce projet."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SurchargeMatriceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        surcharges = serializer.validated_data.get("surcharges", [])
        for item in surcharges:
            role = get_object_or_404(Role, pk=item["role_id"], supprime_le__isnull=True)
            module = item["module"]
            niveau = item.get("niveau")

            if niveau is None:
                # Réinitialisation vers le comportement d'entreprise par défaut
                supprimer_override_permission_projet(projet, role, module)
            else:
                set_override_permission_projet(
                    projet=projet,
                    role=role,
                    module=module,
                    niveau=niveau,
                    modifie_par=request.user,
                )

        matrice = get_matrice_permissions_projet(projet)
        return Response(matrice, status=status.HTTP_200_OK)
