"""Préparation du formulaire à partir de l'identité authentifiée."""

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Utilisateur
from apps.accounts.services.profil import obtenir_donnees_profil
from apps.core.enums import (
    ModeExecution,
    ModuleChoix,
    NiveauAcces,
    RoleProjet,
    StatutUtilisateur,
    TypeBordereau,
    TypeProjet,
)
from apps.core.permissions import PermissionModule
from apps.projets.serializers.contexte_creation import ContexteCreationProjetSerializer
from apps.tiers.models import Tiers


class ContexteCreationProjetView(APIView):
    permission_classes = [
        IsAuthenticated,
        PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE),
    ]

    @extend_schema(
        summary="Préparer la création d'un projet pour l'entreprise connectée",
        responses={200: ContexteCreationProjetSerializer},
    )
    def get(self, request):
        profil = obtenir_donnees_profil(request.user, request=request)
        if not profil["entreprise"]:
            raise PermissionDenied("Une entreprise connectée est requise.")

        def choix(enumeration):
            return [
                {"valeur": valeur, "libelle": libelle}
                for valeur, libelle in enumeration.choices
            ]

        donnees = {
            "utilisateur": profil,
            "entreprise": profil["entreprise"],
            "collaborateurs": Utilisateur.objects.filter(
                is_active=True,
                statut__in=[StatutUtilisateur.ACTIF, StatutUtilisateur.INVITE],
            ).order_by("nom", "prenom", "id"),
            "clients": Tiers.objects.filter(est_actif=True).order_by("raison_sociale", "id"),
            "types_projet": choix(TypeProjet),
            "modes_execution": choix(ModeExecution),
            "types_bordereau": choix(TypeBordereau),
            "roles_projet": choix(RoleProjet),
        }
        return Response(ContexteCreationProjetSerializer(donnees).data)
