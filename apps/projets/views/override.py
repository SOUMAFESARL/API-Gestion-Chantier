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
from apps.core.enums import RoleGlobal, RoleProjet
from apps.core.permissions import MembreDuProjet
from apps.projets.models import AffectationProjet, Projet
from apps.projets.services.overrides import (
    get_matrice_permissions_projet,
    set_override_permission_projet,
    supprimer_override_permission_projet,
)

__all__ = ["ProjetPermissionsRolesView"]


class OverrideInputSerializer(serializers.Serializer):
    role_id = serializers.UUIDField(help_text="Identifiant unique du rôle")
    module = serializers.CharField(help_text="Code du module BTP (ex: CHANTIER, FINANCE, ACHATS)")
    niveau = serializers.IntegerField(
        min_value=0,
        max_value=3,
        required=False,
        allow_null=True,
        help_text="Niveau d'accès (0: AUCUN, 1: LECTURE, 2: ECRITURE, 3: ADMIN, null: réinitialiser au défaut)",
    )
    acces = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        default=None,
        help_text="Liste des droits normalisés (ex: ['lecture', 'saisie'], null pour réinitialiser)",
    )


class SurchargeMatriceInputSerializer(serializers.Serializer):
    surcharges = OverrideInputSerializer(many=True, required=False, default=list)


class ModuleDroitSerializer(serializers.Serializer):
    niveau = serializers.IntegerField(
        help_text="Niveau d'accès (0: AUCUN, 1: LECTURE, 2: ECRITURE, 3: ADMIN)"
    )
    acces = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Liste des droits effectifs (ex: ['lecture', 'saisie', 'validation'])",
    )
    est_surcharge = serializers.BooleanField(
        help_text="True si le droit découle d'une surcharge propre au chantier"
    )


class MatricePermissionProjetRoleSerializer(serializers.Serializer):
    """Ligne de la matrice des habilitations par rôle pour ce chantier."""

    role_id = serializers.UUIDField(help_text="Identifiant du rôle")
    code = serializers.CharField(help_text="Code abrégé du rôle")
    libelle = serializers.CharField(help_text="Libellé complet du rôle")
    est_systeme = serializers.BooleanField(help_text="Rôle système ou personnalisé")
    modules = serializers.DictField(
        child=ModuleDroitSerializer(),
        help_text="Dictionnaire des permissions effectives indexé par code module",
    )


class ProjetPermissionsRolesView(APIView):
    """`GET` et `PUT /api/v1/projets/{id}/permissions-roles/` — Matrice des droits par chantier."""

    permission_classes = [IsAuthenticated, MembreDuProjet]
    parser_classes = [JSONParser]
    serializer_class = SurchargeMatriceInputSerializer

    @extend_schema(
        summary="Matrice des rôles et habilitations effectives sur ce chantier",
        description="Renvoie la matrice complète de tous les rôles actifs et de leurs droits effectifs sur ce projet spécifique.",
        responses={200: MatricePermissionProjetRoleSerializer(many=True)},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        matrice = get_matrice_permissions_projet(projet)
        return Response(matrice, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Appliquer des surcharges de droits sur ce chantier",
        description="Définit ou réinitialise des surcharges de permissions par rôle et par module sur ce chantier.",
        request=SurchargeMatriceInputSerializer,
        responses={200: MatricePermissionProjetRoleSerializer(many=True)},
    )
    def put(self, request, pk):
        # Seul l'administrateur ou le chef de projet assigné peut modifier les droits du chantier
        projet = get_object_or_404(Projet, pk=pk, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)

        from apps.core.droits import a_permission

        peut_gerer_droits = (
            a_permission(request.user, "administration.roles_gerer", request=request)
            or a_permission(request.user, "projets.ecrire", request=request)
        )
        est_chef_projet = (
            projet.chef_projet_id == request.user.id
            or AffectationProjet.objects.filter(
                projet=projet,
                utilisateur=request.user,
                role_projet=RoleProjet.CHEF_PROJET,
                est_actif=True,
                supprime_le__isnull=True,
            ).exists()
        )

        if not (peut_gerer_droits or est_chef_projet):
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
            acces = item.get("acces")

            # Conversion de 'acces' (format Next.js) vers niveau si fourni
            if niveau is None and acces is not None:
                if not acces:
                    niveau = 0
                elif any(str(a).lower() == "validation" for a in acces):
                    niveau = 3
                elif any(str(a).lower() in ("saisie", "ecriture") for a in acces):
                    niveau = 2
                elif any(str(a).lower() == "lecture" for a in acces):
                    niveau = 1
                else:
                    niveau = 0

            if niveau is None and acces is None:
                # Réinitialisation vers le comportement d'entreprise par défaut
                supprimer_override_permission_projet(projet, role, module)
            else:
                set_override_permission_projet(
                    projet=projet,
                    role=role,
                    module=module,
                    niveau=niveau or 0,
                    modifie_par=request.user,
                )

        matrice = get_matrice_permissions_projet(projet)
        return Response(matrice, status=status.HTTP_200_OK)
