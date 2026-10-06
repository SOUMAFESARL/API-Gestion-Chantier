"""Préparation du formulaire à partir de l'identité authentifiée."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
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
from apps.core.droits import APermission
from apps.projets.serializers.contexte_creation import ContexteCreationProjetSerializer
from apps.tiers.models import Tiers


class ContexteCreationProjetView(APIView):
    permission_classes = [
        IsAuthenticated,
        APermission.pour("projets.ecrire"),
    ]

    @extend_schema(
        summary="Charger les choix du formulaire Nouveau projet",
        tags=["projets"],
        description=(
            "À appeler à l'ouverture du formulaire **Nouveau projet**. "
            "Cet appel **ne crée aucun projet** et ne prend aucun corps JSON.\n\n"
            "La réponse contient :\n"
            "- `utilisateur` : profil de la personne connectée.\n"
            "- `entreprise` : entreprise identifiée depuis son jeton.\n"
            "- `collaborateurs` : membres actifs ou invités de cette entreprise. "
            "`assignable_responsable` indique ceux sélectionnables comme CP ou CT.\n"
            "- `clients` : tiers actifs à sélectionner comme maître d'ouvrage.\n"
            "- `types_projet`, `modes_execution`, `types_bordereau`, `roles_projet` : "
            "choix avec `valeur` à envoyer et `libelle` à afficher.\n\n"
            "Conserver les UUID sélectionnés pour `POST /api/v1/projets/`. "
            "Le droit d'écriture sur le module projets est requis. "
            "Pour afficher seulement le profil connecté, utiliser plutôt "
            "`GET /api/v1/auth/profil/`."
        ),
        responses={
            200: ContexteCreationProjetSerializer,
            401: OpenApiResponse(description="Jeton absent, invalide ou expiré."),
            403: OpenApiResponse(
                description="Entreprise requise ou droit de création insuffisant."
            ),
        },
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
