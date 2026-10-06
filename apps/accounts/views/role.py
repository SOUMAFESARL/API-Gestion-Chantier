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
from apps.core.enums import RoleGlobal
from apps.core.exceptions import ActionReserveeDg, RoleSubstitutionObligatoire

__all__ = [
    "ParametresRoleDetailUpdateView",
    "ParametresRoleListCreateView",
    "ParametresRoleSupprimerReassignerView",
    "RoleDetailUpdateView",
    "RoleListCreateView",
    "RoleSupprimerReassignerView",
]


def _autoriser_roles_dg(user):
    """Règle R-DEMO-08 : Seul le DG / Propriétaire a autorité sur les routes /api/v1/roles/."""
    if not user or not user.is_authenticated:
        raise ActionReserveeDg()
    if not (getattr(user, "is_dg", False) or getattr(user, "is_owner", False)):
        raise ActionReserveeDg()


def _autoriser_parametres_roles(user, request=None):
    """Autorise administration.roles_gerer pour les routes parametres/roles."""
    if not user or not user.is_authenticated:
        raise ActionReserveeDg()
    from apps.core.droits import a_permission
    if not a_permission(user, "administration.roles_gerer", request=request):
        raise ActionReserveeDg()


class RoleListCreateView(APIView):
    """`GET` et `POST /api/v1/roles/` — Consultation et création des rôles de l'entreprise."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les rôles de l'entreprise",
        responses={200: RoleSerializer(many=True)},
    )
    def get(self, request):
        _autoriser_roles_dg(request.user)

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
        _autoriser_roles_dg(request.user)

        serializer = RoleCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role = creer_role(
                code=serializer.validated_data["code"],
                libelle=serializer.validated_data["libelle"],
                description=serializer.validated_data.get("description", ""),
                permissions_modules=serializer.validated_data.get("permissions_modules", {}),
                portee=serializer.validated_data.get("portee", "PROJET"),
                cree_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = RoleDetailSerializer(role)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class RoleDetailUpdateView(APIView):
    """`GET`, `PATCH` et `POST /api/v1/roles/{id}/` — Détail et modification d'un rôle."""

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
        _autoriser_roles_dg(request.user)

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)

        if role.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
            return Response(
                {
                    "erreur": {
                        "code": "modification_dg_interdite",
                        "message": "Le rôle Directeur Général est immuable et ne peut pas être modifié.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RoleModificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        nouvelle_portee = serializer.validated_data.get("portee")
        if nouvelle_portee is not None:
            from apps.core.droits import est_dg
            if not est_dg(request.user):
                return Response(
                    {"detail": _("Seul le Directeur Général peut modifier la portée d'un rôle.")},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if role.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
                return Response(
                    {"detail": _("La portée du rôle Directeur Général ne peut pas être modifiée.")},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if nouvelle_portee != role.portee:
                confirmer = serializer.validated_data.get("confirmer", False)
                if not confirmer:
                    from apps.accounts.models import Utilisateur
                    from apps.core.enums import StatutUtilisateur
                    personnes_touchees = Utilisateur.objects.filter(
                        role=role,
                        statut=StatutUtilisateur.ACTIF,
                        supprime_le__isnull=True,
                    ).count()
                    return Response(
                        {
                            "code": "confirmation_requise",
                            "personnes_touchees": personnes_touchees,
                            "message": _("Confirmation requise pour le changement de portée."),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                if nouvelle_portee == "ENTREPRISE":
                    from apps.accounts.models import Utilisateur
                    from apps.projets.models import AffectationProjet
                    users_with_role = Utilisateur.objects.filter(role=role, supprime_le__isnull=True)
                    AffectationProjet.objects.filter(utilisateur__in=users_with_role, est_actif=True).update(est_actif=False)

        try:
            role_modifie = modifier_role(
                role=role,
                libelle=serializer.validated_data.get("libelle"),
                description=serializer.validated_data.get("description"),
                permissions_modules=serializer.validated_data.get("permissions_modules"),
                portee=nouvelle_portee,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = RoleDetailSerializer(role_modifie)
        return Response(retour.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un rôle et sa matrice de permissions (POST)",
        request=RoleModificationSerializer,
        responses={200: RoleDetailSerializer},
    )
    def post(self, request, pk):
        return self.patch(request, pk)


class RoleSupprimerReassignerView(APIView):
    """`POST /api/v1/roles/{id}/supprimer/` — Suppression d'un rôle (réservée au DG)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Supprimer un rôle (avec réassignation ou suppression en cascade des collaborateurs)",
        request=RoleSuppressionSerializer,
        responses={200: dict},
    )
    def post(self, request, pk):
        _autoriser_roles_dg(request.user)

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)

        if role.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
            return Response(
                {
                    "erreur": {
                        "code": "suppression_dg_interdite",
                        "message": "Le rôle Directeur Général ne peut pas être supprimé : les rôles système ne peuvent pas être supprimés.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role.code in (RoleGlobal.ADMIN, "AD"):
            est_dg_ou_owner = (
                getattr(request.user, "is_dg", False)
                or getattr(request.user, "is_owner", False)
                or getattr(request.user, "role_global", None) == RoleGlobal.DIRECTEUR_GENERAL
            )
            if not est_dg_ou_owner:
                raise ActionReserveeDg()

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)

        serializer = RoleSuppressionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        substitution_id = serializer.validated_data.get("role_substitution_id") or serializer.validated_data.get(
            "reassigner_vers_role_id"
        )
        supprimer_collaborateurs = serializer.validated_data.get("supprimer_collaborateurs", False)

        if not substitution_id and not supprimer_collaborateurs:
            raise RoleSubstitutionObligatoire()

        reassigner_vers_role = None
        if substitution_id:
            reassigner_vers_role = get_object_or_404(Role, pk=substitution_id, supprime_le__isnull=True)

        try:
            resultat = supprimer_role(
                role=role,
                reassigner_vers_role=reassigner_vers_role,
                supprimer_collaborateurs=supprimer_collaborateurs,
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


# ============================================================================
# Vues dédiées pour /api/v1/parametres/roles/ (AD + DG autorisés)
# ============================================================================


class ParametresRoleListCreateView(APIView):
    """`GET` et `POST /api/v1/parametres/roles/` — Consultation et création des rôles dans les paramètres."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les rôles et permissions par module (Paramètres)",
        responses={200: RoleSerializer(many=True)},
    )
    def get(self, request):
        if not Role.objects.filter(supprime_le__isnull=True).exists():
            initialiser_roles_par_defaut()

        roles = Role.objects.filter(supprime_le__isnull=True).order_by("code")
        serializer = RoleSerializer(roles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un rôle personnalisé avec sa matrice de permissions (Paramètres)",
        request=RoleCreationSerializer,
        responses={201: RoleDetailSerializer},
    )
    def post(self, request):
        _autoriser_parametres_roles(request.user, request=request)

        serializer = RoleCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role = creer_role(
                code=serializer.validated_data["code"],
                libelle=serializer.validated_data["libelle"],
                description=serializer.validated_data.get("description", ""),
                permissions_modules=serializer.validated_data.get("permissions_modules", {}),
                portee=serializer.validated_data.get("portee", "PROJET"),
                cree_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = RoleDetailSerializer(role)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class ParametresRoleDetailUpdateView(APIView):
    """`GET`, `POST` et `PATCH /api/v1/parametres/roles/{id}/` — Détail et modification d'un rôle dans les paramètres."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'un rôle et permissions par module (Paramètres)",
        responses={200: RoleDetailSerializer},
    )
    def get(self, request, pk):
        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)
        serializer = RoleDetailSerializer(role)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un rôle et sa matrice de permissions (Paramètres - PATCH)",
        request=RoleModificationSerializer,
        responses={200: RoleDetailSerializer},
    )
    def patch(self, request, pk):
        _autoriser_parametres_roles(request.user, request=request)

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)

        if role.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
            return Response(
                {
                    "erreur": {
                        "code": "modification_dg_interdite",
                        "message": "Le rôle Directeur Général est immuable et ne peut pas être modifié.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RoleModificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        nouvelle_portee = serializer.validated_data.get("portee")
        if nouvelle_portee is not None:
            from apps.core.droits import est_dg
            if not est_dg(request.user):
                return Response(
                    {"detail": _("Seul le Directeur Général peut modifier la portée d'un rôle.")},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if role.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
                return Response(
                    {"detail": _("La portée du rôle Directeur Général ne peut pas être modifiée.")},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if nouvelle_portee != role.portee:
                confirmer = serializer.validated_data.get("confirmer", False)
                if not confirmer:
                    from apps.accounts.models import Utilisateur
                    from apps.core.enums import StatutUtilisateur
                    personnes_touchees = Utilisateur.objects.filter(
                        role=role,
                        statut=StatutUtilisateur.ACTIF,
                        supprime_le__isnull=True,
                    ).count()
                    return Response(
                        {
                            "code": "confirmation_requise",
                            "personnes_touchees": personnes_touchees,
                            "message": _("Confirmation requise pour le changement de portée."),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                if nouvelle_portee == "ENTREPRISE":
                    from apps.accounts.models import Utilisateur
                    from apps.projets.models import AffectationProjet
                    users_with_role = Utilisateur.objects.filter(role=role, supprime_le__isnull=True)
                    AffectationProjet.objects.filter(utilisateur__in=users_with_role, est_actif=True).update(est_actif=False)

        try:
            role_modifie = modifier_role(
                role=role,
                libelle=serializer.validated_data.get("libelle"),
                description=serializer.validated_data.get("description"),
                permissions_modules=serializer.validated_data.get("permissions_modules"),
                portee=nouvelle_portee,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        retour = RoleDetailSerializer(role_modifie)
        return Response(retour.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier un rôle et sa matrice de permissions (Paramètres - POST)",
        request=RoleModificationSerializer,
        responses={200: RoleDetailSerializer},
    )
    def post(self, request, pk):
        return self.patch(request, pk)


class ParametresRoleSupprimerReassignerView(APIView):
    """`POST /api/v1/parametres/roles/{id}/supprimer/` — Suppression d'un rôle avec réassignation ou suppression cascade."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Supprimer un rôle personnalisé avec réassignation ou suppression cascade (Paramètres)",
        request=RoleSuppressionSerializer,
        responses={200: dict},
    )
    def post(self, request, pk):
        _autoriser_parametres_roles(request.user, request=request)

        role = get_object_or_404(Role, pk=pk, supprime_le__isnull=True)

        if role.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
            return Response(
                {
                    "erreur": {
                        "code": "suppression_dg_interdite",
                        "message": "Le rôle Directeur Général ne peut pas être supprimé : les rôles système ne peuvent pas être supprimés.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Protection du rôle Administrateur : seul le DG / Propriétaire a autorité pour le supprimer
        if role.code in (RoleGlobal.ADMIN, "AD"):
            est_dg_ou_owner = (
                getattr(request.user, "is_dg", False)
                or getattr(request.user, "is_owner", False)
                or getattr(request.user, "role_global", None) == RoleGlobal.DIRECTEUR_GENERAL
            )
            if not est_dg_ou_owner:
                raise ActionReserveeDg()

        serializer = RoleSuppressionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        substitution_id = serializer.validated_data.get("role_substitution_id") or serializer.validated_data.get(
            "reassigner_vers_role_id"
        )
        supprimer_collaborateurs = serializer.validated_data.get("supprimer_collaborateurs", False)

        if not substitution_id and not supprimer_collaborateurs:
            raise RoleSubstitutionObligatoire()

        reassigner_vers_role = None
        if substitution_id:
            reassigner_vers_role = get_object_or_404(Role, pk=substitution_id, supprime_le__isnull=True)

        try:
            resultat = supprimer_role(
                role=role,
                reassigner_vers_role=reassigner_vers_role,
                supprimer_collaborateurs=supprimer_collaborateurs,
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
