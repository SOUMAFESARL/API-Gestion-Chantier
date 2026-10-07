"""Vues API pour la gestion de l'équipe de chantier / affectations (US-04 / E-05 / C-05)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur
from apps.core.permissions import GardePermissionProjet, obtenir_portee_role
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

__all__ = [
    "CollaborateursAffectablesView",
    "ProjetAffectationDetailView",
    "ProjetAffectationListCreateView",
]


class ProjetAffectationListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/{projet_id}/affectations/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                GardePermissionProjet.pour("projets.affecter_membres")(),
            ]
        return [
            IsAuthenticated(),
            GardePermissionProjet.pour("projets.lire")(),
        ]

    @extend_schema(
        summary="Lister les membres de l'équipe du chantier",
        description="Renvoie tous les collaborateurs affectés au projet avec leurs rôles et statuts.",
        responses={200: AffectationProjetResponseSerializer(many=True)},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        actifs_seulement = request.query_params.get("actifs_seulement", "false").lower() == "true"
        qs = lister_affectations_projet(projet, actifs_seulement=actifs_seulement)
        serializer = AffectationProjetResponseSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Affecter un collaborateur au chantier",
        description="Associe un collaborateur à ce projet avec un rôle spécifique (CT, CC, Consultant lecture, MOE, MOA, etc.).",
        request=AffectationProjetCreateSerializer,
        responses={201: AffectationProjetResponseSerializer},
    )
    def post(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)

        serializer = AffectationProjetCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            affectation = affecter_collaborateur_projet(
                projet=projet,
                utilisateur=serializer.validated_data["utilisateur_instance"],
                role_projet=serializer.validated_data["role_projet"],
                date_debut=serializer.validated_data.get("date_debut"),
                date_fin=serializer.validated_data.get("date_fin"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(
            AffectationProjetResponseSerializer(affectation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjetAffectationDetailView(APIView):
    """`GET`, `PATCH` et `DELETE /api/v1/projets/{projet_id}/affectations/{pk}/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [
                IsAuthenticated(),
                GardePermissionProjet.pour("projets.affecter_membres")(),
            ]
        return [
            IsAuthenticated(),
            GardePermissionProjet.pour("projets.lire")(),
        ]

    @extend_schema(
        summary="Détail d'une affectation de chantier",
        responses={200: AffectationProjetResponseSerializer},
    )
    def get(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur"),
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )
        return Response(
            AffectationProjetResponseSerializer(affectation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Modifier une affectation ou désactiver un collaborateur",
        request=AffectationProjetUpdateSerializer,
        responses={200: AffectationProjetResponseSerializer},
    )
    def patch(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)

        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur"),
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

        return Response(
            AffectationProjetResponseSerializer(affectation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Révoquer ou supprimer une affectation de chantier",
        responses={204: None},
    )
    def delete(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)

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


class CollaborateursAffectablesView(APIView):
    """`GET /api/v1/projets/{projet_id}/collaborateurs-affectables/` (L5-1 / C-05 puce 2)."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.affecter_membres"),
    ]

    @extend_schema(
        summary="Liste réduite des collaborateurs affectables au chantier",
        description=(
            "Retourne la liste des collaborateurs actifs dont le rôle est à portée PROJET. "
            "Champs limités à id, nom, role. Exclut toute information personnelle (email, téléphone) "
            "et les rôles de portée ENTREPRISE (DG, AD, DO)."
        ),
        responses={200: serializers.ListSerializer(child=serializers.DictField())},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)

        candidats = (
            Utilisateur.objects.filter(
                is_active=True,
                statut=StatutUtilisateur.ACTIF,
                supprime_le__isnull=True,
            )
            .select_related("role")
            .order_by("nom", "prenom")
        )

        resultats = []
        for u in candidats:
            portee = obtenir_portee_role(u)
            if portee == "ENTREPRISE":
                continue

            role_libelle = u.role.libelle if u.role else (u.role_global or "")
            nom_complet = f"{u.prenom} {u.nom}".strip() or u.nom
            resultats.append(
                {
                    "id": u.id,
                    "nom": nom_complet,
                    "role": role_libelle,
                }
            )

        return Response(resultats, status=status.HTTP_200_OK)
