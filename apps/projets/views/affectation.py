"""Vues API pour la gestion de l'équipe de chantier / affectations (US-04)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import RoleGlobal
from apps.projets.models import AffectationProjet, Projet
from apps.projets.serializers.affectation import (
    AffectationProjetCreateSerializer,
    AffectationProjetResponseSerializer,
    AffectationProjetUpdateSerializer,
)
from apps.projets.services.affectations import (
    affecter_collaborateur_projet,
    lister_affectations_projet,
    modifier_affectation_projet,
    revoquer_affectation_projet,
)

__all__ = ["ProjetAffectationDetailView", "ProjetAffectationListCreateView"]


def _verifier_droits_gestion_equipe(user, projet: Projet):
    """Autorise l'administrateur, le DG ou le Chef de Projet assigné à ce chantier."""
    if not user or not user.is_authenticated:
        raise PermissionDenied(_("Authentification requise."))

    est_admin = (
        getattr(user, "is_owner", False)
        or getattr(user, "is_dg", False)
        or getattr(user, "role_global", None) in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
        or getattr(user, "is_superuser", False)
    )
    est_cp_du_projet = (
        projet.chef_projet_id == user.id
        or getattr(user, "role_global", None) == RoleGlobal.CHEF_PROJET
    )

    if not (est_admin or est_cp_du_projet):
        raise PermissionDenied(_("Seul le Chef de Projet assigné ou la Direction peut gérer l'équipe du chantier."))


class ProjetAffectationListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/{projet_id}/affectations/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les membres de l'équipe du chantier",
        description="Renvoie tous les collaborateurs affectés au projet avec leurs rôles et statuts.",
        responses={200: AffectationProjetResponseSerializer(many=True)},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        actifs_seulement = request.query_params.get("actifs_seulement", "false").lower() == "true"
        qs = lister_affectations_projet(projet, actifs_seulement=actifs_seulement)
        serializer = AffectationProjetResponseSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Affecter un collaborateur au chantier",
        description="Associe un collaborateur à ce projet avec un rôle spécifique (CT, CC, Consultant lecture, MOE, MOA, etc.).",
        request=AffectationProjetCreateSerializer,
        responses={201: AffectationProjetResponseSerializer},
    )
    def post(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        _verifier_droits_gestion_equipe(request.user, projet)

        serializer = AffectationProjetCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            affectation = affecter_collaborateur_projet(
                projet=projet,
                utilisateur=serializer.validated_data["utilisateur_instance"],
                role_projet=serializer.validated_data["role_projet"],
                date_debut=serializer.validated_data.get("date_debut"),
                date_fin=serializer.validated_data.get("date_fin"),
                role_personnalise=serializer.validated_data.get("role_instance"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(AffectationProjetResponseSerializer(affectation).data, status=status.HTTP_201_CREATED)


class ProjetAffectationDetailView(APIView):
    """`GET`, `PATCH` et `DELETE /api/v1/projets/{projet_id}/affectations/{pk}/`."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'une affectation de chantier",
        responses={200: AffectationProjetResponseSerializer},
    )
    def get(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur", "role"),
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )
        return Response(AffectationProjetResponseSerializer(affectation).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier une affectation ou désactiver un collaborateur",
        request=AffectationProjetUpdateSerializer,
        responses={200: AffectationProjetResponseSerializer},
    )
    def patch(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        _verifier_droits_gestion_equipe(request.user, projet)

        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur", "role"),
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )

        serializer = AffectationProjetUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            affectation = modifier_affectation_projet(
                affectation=affectation,
                donnees=serializer.validated_data,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(AffectationProjetResponseSerializer(affectation).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Révoquer ou supprimer une affectation de chantier",
        responses={204: None},
    )
    def delete(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        _verifier_droits_gestion_equipe(request.user, projet)

        affectation = get_object_or_404(
            AffectationProjet,
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )

        suppression_physique = request.query_params.get("hard", "false").lower() == "true"

        try:
            revoquer_affectation_projet(
                affectation=affectation,
                suppression_physique=suppression_physique,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(status=status.HTTP_204_NO_CONTENT)
