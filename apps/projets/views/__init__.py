from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.permissions import (
    MembreDuProjet,
    PermissionModule,
    filtrer_queryset_par_affectations,
)
from apps.projets.models import Projet
from apps.projets.serializers import ProjetCreationSerializer, ProjetSerializer
from apps.projets.serializers.swagger import ProjetPatchSerializer, ProjetPostSerializer
from apps.projets.views.meteo import MeteoProjetView, ReferentielVillesView
from apps.projets.views.override import ProjetPermissionsRolesView
from apps.projets.views.tableau_de_bord import TableauDeBordView

__all__ = [
    "MeteoProjetView",
    "ProjetDetailView",
    "ProjetListCreateView",
    "ProjetPermissionsRolesView",
    "ReferentielVillesView",
    "TableauDeBordView",
]


class ProjetListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
        ]

    @extend_schema(
        summary="Afficher la liste des projets accessibles",
        tags=["projets"],
        description=(
            "À appeler à l'ouverture de la page **Projets**, puis après une création.\n\n"
            "Renvoie un **tableau JSON non paginé** (`[]` si aucun projet). "
            "La direction et les administrateurs voient tous les projets de leur entreprise ; "
            "les collaborateurs voient uniquement leurs projets affectés. "
            "La lecture du module projets est requise.\n\n"
            "Chaque projet comprend notamment sa référence, son client, ses responsables, "
            "ses lots, son créateur (`cree_par`) et son entreprise. "
            "Le jeton Bearer identifie l'utilisateur et l'entreprise : aucun identifiant "
            "d'entreprise n'est à fournir dans l'URL."
        ),
        responses={
            200: ProjetSerializer(many=True),
            401: OpenApiResponse(description="Jeton absent, invalide ou expiré."),
            403: OpenApiResponse(description="Lecture du module projets non autorisée."),
        },
    )
    def get(self, request):
        qs = (
            Projet.objects.all()
            .select_related("client", "chef_projet", "conducteur_travaux", "cree_par")
            .prefetch_related("lots")
        )
        qs = filtrer_queryset_par_affectations(qs, request.user, champ_projet="id", request=request)
        serializer = ProjetSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Enregistrer le formulaire Nouveau projet",
        tags=["projets"],
        description=(
            "À appeler au clic sur **Créer le projet**. La direction peut envoyer uniquement "
            "l'identification : nom, type_projet, ville, maitre_ouvrage "
            "et maitre_oeuvre facultatif. "
            "Planning, budget, lots et responsables peuvent être définis ensuite via PATCH ; "
            "les autres membres utilisent les routes d'affectations. "
            "La création complète avec lots et équipe reste disponible.\n\n"
            "**Lignes de lots** : ajouter ou retirer les lignes dans le formulaire, puis envoyer "
            "toutes les lignes restantes dans `lots`. Aucun appel DELETE avant la création. "
            "Chaque ligne exige `libelle`. Les codes automatiques évitent les codes saisis.\n\n"
            "**Avant de commencer** : appeler `GET /api/v1/projets/contexte-creation/` "
            "pour récupérer les UUID réels des collaborateurs ainsi que les "
            "valeurs autorisées des listes. Les UUID de l'exemple sont fictifs et doivent "
            "être remplacés.\n\n"
            "- `maitre_ouvrage` : nom saisi librement, obligatoire. "
            "`maitre_oeuvre` : texte facultatif.\n"
            "- Compatibilité : un UUID `client` existant peut remplacer `maitre_ouvrage`, "
            "mais ne pas envoyer les deux. Aucun client à créer pour la saisie libre.\n"
            "- `budget_initial_montant` : centimes de FCFA ; **2 000 FCFA = 200000**.\n"
            "- Les dates sont facultatives et peuvent être nulles. Si les deux sont définies, "
            "`date_fin_prevue` doit être strictement postérieure au début.\n"
            "- `reference` et les codes des lots sont générés si omis.\n"
            "- Le chef de projet est facultatif pour la direction à la création ; "
            "il reste requis pour une création par un collaborateur. "
            "les autres membres et les lots sont optionnels.\n"
            "- Utiliser des membres distincts pour les différents rôles. "
            "Un DG ou propriétaire ne peut pas être chef de projet ou conducteur de travaux.\n"
            "- Les rôles Directeur financier et Bailleur ne font pas partie de ce contrat.\n\n"
            "**Identité automatique** : ne pas envoyer `cree_par`, `utilisateur_id`, "
            "`entreprise_id` ou `schema`. Le créateur et l'entreprise viennent de "
            "l'authentification. Le créateur n'est pas nécessairement le chef de projet.\n\n"
            "Après le succès **201**, rappeler `GET /api/v1/projets/` pour actualiser la liste."
        ),
        request=ProjetPostSerializer,
        responses={
            201: OpenApiResponse(
                ProjetSerializer,
                description="Projet créé ; planning et équipe peuvent être absents.",
            ),
            400: OpenApiResponse(
                description="Champs invalides, dates incohérentes ou membre indisponible."
            ),
            401: OpenApiResponse(description="Jeton absent, invalide ou expiré."),
            403: OpenApiResponse(description="Écriture sur le module projets non autorisée."),
            422: OpenApiResponse(description="DG/propriétaire non assignable comme responsable."),
        },
        examples=[
            OpenApiExample(
                "Identification seule — entreprise connectée",
                request_only=True,
                value={
                    "nom": "Immeuble Les Palmiers R+5",
                    "type_projet": "BATIMENT_RESIDENTIEL",
                    "ville": "Abidjan",
                    "maitre_ouvrage": "Entreprise cliente",
                    "maitre_oeuvre": "Cabinet d'études",
                },
            ),
            OpenApiExample(
                "Formulaire complet — informations, lots et équipe",
                request_only=True,
                value={
                    "nom": "ZRAN",
                    "type_projet": "BATIMENT_COMMERCIAL",
                    "maitre_ouvrage": "SOUMAFE BTP",
                    "maitre_oeuvre": "Cabinet d'études",
                    "ville": "Adjamé",
                    "date_debut_prevue": "2026-10-01",
                    "date_fin_prevue": "2026-12-31",
                    "budget_initial_montant": 200000,
                    "description": "Construction du bâtiment ZRAN",
                    "lots": [
                        {
                            "libelle": "Gros œuvre",
                            "mode_execution": "SOUS_TRAITANCE_STRUCTUREE",
                            "type_bordereau": "PRIX_UNITAIRE",
                            "date_debut_prevue": "2026-10-01",
                            "date_fin_prevue": "2026-11-15",
                        },
                        {
                            "libelle": "Plomberie",
                            "mode_execution": "REGIE",
                            "type_bordereau": "PRIX_UNITAIRE",
                        },
                    ],
                    "equipe": {
                        "chef_projet_id": "22222222-2222-4222-8222-222222222222",
                        "conducteur_travaux_id": "33333333-3333-4333-8333-333333333333",
                        "chefs_chantier_ids": ["44444444-4444-4444-8444-444444444444"],
                        "visiteurs_ids": [],
                    },
                },
            ),
        ],
    )
    def post(self, request):
        serializer = ProjetCreationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        projet_charge = (
            Projet.objects.select_related("client", "chef_projet", "conducteur_travaux", "cree_par")
            .prefetch_related("lots")
            .get(pk=projet.pk)
        )
        retour = ProjetSerializer(projet_charge, context={"request": request})
        return Response(retour.data, status=status.HTTP_201_CREATED)


class ProjetDetailView(APIView):
    """Lecture, modification partielle et suppression logique d'un projet."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [
                IsAuthenticated(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
                MembreDuProjet(),
            ]
        return [
            IsAuthenticated(),
            PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)(),
            MembreDuProjet(),
        ]

    @extend_schema(
        summary="Détail d'un projet",
        tags=["projets"],
        description=(
            "À appeler lorsqu'un utilisateur ouvre un projet depuis la liste. "
            "Remplacer `{id}` dans l'URL par l'UUID `id` renvoyé par la liste ou la création. "
            "La lecture du module et l'accès à ce projet sont contrôlés côté serveur. "
            "Pour consulter toutes les affectations de l'équipe, utiliser "
            "`GET /api/v1/projets/{id}/affectations/`."
        ),
        responses={
            200: ProjetSerializer,
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.select_related(
                "client", "chef_projet", "conducteur_travaux", "cree_par"
            ).prefetch_related("lots"),
            pk=pk,
        )
        self.check_object_permissions(request, projet)
        return Response(
            ProjetSerializer(projet, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Modifier un projet",
        tags=["projets"],
        description=(
            "Modification partielle des informations générales et des responsables par UUID. "
            "Après une création avec identification seule, renseigner ici les dates, le budget "
            "et chef_projet_id. Omettre ce dernier tant qu'aucun chef n'est choisi ; "
            "chef_projet_id=null est refusé. "
            "Les champs absents sont conservés ; conducteur_travaux_id=null retire le conducteur. "
            "lots ajoute des lignes ; lots_supprimer_ids supprime les UUID indiqués. "
            "Les lots non mentionnés restent inchangés. "
            "Les listes vides ne suppriment aucun lot. Chaque nouveau lot exige `libelle`. "
            "Les UUID à supprimer proviennent du détail de ce projet. La suppression est logique "
            "et conserve les rapports. Une erreur annule toute la modification. "
            "La réponse contient la liste actualisée des lots actifs. "
            "Les ajouts ne sont pas idempotents : ne pas rejouer aveuglément une requête. "
            "L'objet equipe, les invitations et les listes de membres sont réservés "
            "à la création et sont refusés ici. Utiliser les routes d'affectations pour l'équipe."
        ),
        request=ProjetPatchSerializer,
        responses={
            200: ProjetSerializer,
            400: OpenApiResponse(
                description="Champs invalides, code en doublon, chef absent ou lot hors projet."
            ),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Écriture ou accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
            422: OpenApiResponse(description="DG/propriétaire non assignable comme responsable."),
        },
        examples=[
            OpenApiExample(
                "Ajouter deux lots",
                request_only=True,
                value={
                    "lots": [{"libelle": "Électricité"}, {"libelle": "Plomberie"}],
                },
            ),
            OpenApiExample(
                "Supprimer deux lots",
                request_only=True,
                value={
                    "lots_supprimer_ids": [
                        "55555555-5555-4555-8555-555555555555",
                        "66666666-6666-4666-8666-666666666666",
                    ],
                },
                description="Remplacer ces UUID fictifs par les UUID des lots du projet.",
            ),
            OpenApiExample(
                "Ajouter et supprimer ensemble",
                request_only=True,
                value={
                    "lots": [{"libelle": "Menuiserie"}, {"libelle": "Peinture"}],
                    "lots_supprimer_ids": ["55555555-5555-4555-8555-555555555555"],
                },
            ),
            OpenApiExample(
                "Modifier les informations",
                request_only=True,
                value={
                    "nom": "ZRAN - phase 2",
                    "conducteur_travaux_id": None,
                },
            ),
        ],
    )
    @transaction.atomic
    def patch(self, request, pk):
        projet = get_object_or_404(Projet.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, projet)
        serializer = ProjetCreationSerializer(
            projet, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        projet_charge = (
            Projet.objects.select_related("client", "chef_projet", "conducteur_travaux", "cree_par")
            .prefetch_related("lots")
            .get(pk=projet.pk)
        )
        retour = ProjetSerializer(projet_charge, context={"request": request})
        return Response(retour.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer un projet",
        tags=["projets"],
        description="Suppression logique : conserve les lots et l'historique en base.",
        request=None,
        responses={
            204: OpenApiResponse(description="Projet supprimé, réponse sans corps."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Écriture ou accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou déjà supprimé."),
        },
    )
    def delete(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        projet.delete(utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
