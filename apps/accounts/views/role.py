"""Vues API pour la gestion dynamique des rôles et des habilitations par module."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.serializers import (
    RoleCreationSerializer,
    RoleDetailSerializer,
    RoleModificationSerializer,
    RoleSerializer,
    RoleSuppressionSerializer,
)
from apps.accounts.services.roles import (
    creer_role,
    initialiser_roles_par_defaut,
    modifier_role,
    supprimer_role,
)
from apps.core.exceptions import ActionReserveeDg, RoleSubstitutionObligatoire

__all__ = [
    "RoleDetailUpdateView",
    "RoleListCreateView",
    "RoleSupprimerReassignerView",
]


class RoleListCreateView(APIView):
    """`GET` et `POST /api/v1/roles/` — Consultation et création des rôles de l'entreprise."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les rôles de l'entreprise",
        responses={200: RoleSerializer(many=True)},
    )
    def get(self, request):
        # Initialise les rôles par défaut s'ils n'existent pas encore
        if not Role.objects.filter(supprime_le__isnull=True).exists():
            initialiser_roles_par_defaut()

        roles = Role.objects.filter(supprime_le__isnull=True).order_by("code")
        serializer = RoleSerializer(roles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un rôle personnalisé",
        request=RoleCreationSerializer,
        responses={201: RoleDetailSerializer},
    )
    def post(self, request):
        # Règle R-DEMO-08 : Seul le DG / Propriétaire a autorité sur les rôles
        if not (getattr(request.user, "is_dg", False) or getattr(request.user, "is_owner", False)):
            raise ActionReserveeDg()

        serializer = RoleCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role = creer_role(
                code=serializer.validated_data["code"],
                libelle=serializer.validated_data["libelle"],
                description=serializer.validated_data.get("description", ""),
                permissions_modules=serializer.validated_data.get("permissions_modules", {}),
                cree_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = RoleDetailSerializer(role)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class RoleDetailUpdateView(APIView):
    """`GET` et `PATCH /api/v1/roles/{id}/` — Détail et modification d'un rôle."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'un rôle avec sa matrice de permissions",
        responses={200: RoleDetailSerializer},
    )
    def get(self, request, pk):
        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)
        serializer = RoleDetailSerializer(role)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un rôle et sa matrice de permissions",
        request=RoleModificationSerializer,
        responses={200: RoleDetailSerializer},
    )
    def patch(self, request, pk):
        # Règle R-DEMO-08 : Seul le DG / Propriétaire a autorité sur les rôles
        if not (getattr(request.user, "is_dg", False) or getattr(request.user, "is_owner", False)):
            raise ActionReserveeDg()

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)
        serializer = RoleModificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role_modifie = modifier_role(
                role=role,
                libelle=serializer.validated_data.get("libelle"),
                description=serializer.validated_data.get("description"),
                permissions_modules=serializer.validated_data.get("permissions_modules"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = RoleDetailSerializer(role_modifie)
        return Response(retour.data, status=status.HTTP_200_OK)


class RoleSupprimerReassignerView(APIView):
    """`POST /api/v1/roles/{id}/supprimer/` — Suppression d'un rôle avec réassignation."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Supprimer un rôle avec réassignation des utilisateurs",
        request=RoleSuppressionSerializer,
        responses={200: dict},
    )
    def post(self, request, pk):
        # Règle R-DEMO-08 : Seul le DG / Propriétaire a autorité sur les rôles
        if not (getattr(request.user, "is_dg", False) or getattr(request.user, "is_owner", False)):
            raise ActionReserveeDg()

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)

        # Substitution obligatoire (REC-S1-10-B)
        substitution_id = request.data.get("role_substitution_id") or request.data.get(
            "reassigner_vers_role_id"
        )
        if not substitution_id:
            raise RoleSubstitutionObligatoire()

        serializer = RoleSuppressionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reassigner_vers_role = get_object_or_404(Role, pk=substitution_id, supprime_le__isnull=True)

        try:
            resultat = supprimer_role(
                role=role,
                reassigner_vers_role=reassigner_vers_role,
                supprime_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(
            {
                "message": _("Rôle supprimé avec succès."),
                **resultat,
            },
            status=status.HTTP_200_OK,
        )
