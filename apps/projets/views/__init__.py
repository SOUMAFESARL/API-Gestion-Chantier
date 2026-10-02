from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces
from apps.core.permissions import (
    EstDirection,
    MembreDuProjet,
    PermissionModule,
    filtrer_queryset_par_affectations,
)
from apps.projets.models import Projet
from apps.projets.serializers.swagger import (
    ProjetCreationResponseSerializer,
    ProjetPatchSerializer,
    ProjetPostSerializer,
)
from apps.projets.views.activite import (
    ActiviteDetailView,
    LotActiviteListCreateView,
)
from apps.projets.views.meteo import MeteoProjetView, ReferentielVillesView
from apps.projets.views.override import ProjetPermissionsRolesView
from apps.projets.views.reprogrammation import (
    ActiviteHistoriqueDatesView,
    ActiviteReprogrammerView,
    GlobalJournalReportsView,
    LotHistoriqueDatesView,
    LotReprogrammerView,
    MotifReportListCreateView,
    ProjetHistoriqueDatesView,
    ProjetJournalReportsConsolideView,
    ProjetReprogrammerView,
)
from apps.projets.views.tableau_de_bord import TableauDeBordView

__all__ = [
    "ActiviteDetailView",
    "ActiviteHistoriqueDatesView",
    "ActiviteReprogrammerView",
    "GlobalJournalReportsView",
    "LotActiviteListCreateView",
    "LotHistoriqueDatesView",
    "LotReprogrammerView",
    "MeteoProjetView",
    "MotifReportListCreateView",
    "ProjetDetailView",
    "ProjetHistoriqueDatesView",
    "ProjetJournalReportsConsolideView",
    "ProjetListCreateView",
    "ProjetPermissionsRolesView",
    "ProjetReprogrammerView",
    "ReferentielVillesView",
    "TableauDeBordView",
]


class ProjetListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                EstDirection(),
                PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.ECRITURE)(),
            ]
        if self.request.method in ("PUT", "PATCH", "DELETE"):
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
            "Liste des projets accessibles, limitee aux onze champs du formulaire. "
            "La reference identifie chaque projet dans la liste. "
            "Le POST retourne son URL dans l'entete Location."
        ),
        responses={
            200: ProjetCreationResponseSerializer(many=True),
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
        serializer = ProjetCreationResponseSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Creer un projet depuis le formulaire Nouveau projet",
        tags=["projets"],
        description=(
            "Nom, type, ville et maitre_ouvrage sont obligatoires. "
            "Maitre_oeuvre, dates, budget et description sont facultatifs. "
            "Reference et duree sont calculees automatiquement. "
            "Budget en centimes FCFA. Fin strictement apres debut. "
            "Les champs hors formulaire sont refuses ; lots et equipe "
            "s'ajoutent ensuite depuis le projet."
        ),
        request=ProjetPostSerializer,
        responses={201: ProjetCreationResponseSerializer},
        examples=[
            OpenApiExample(
                "Formulaire Nouveau projet",
                request_only=True,
                value={
                    "nom": "Immeuble Les Palmiers R+5",
                    "type_projet": "BATIMENT_RESIDENTIEL",
                    "ville": "Man",
                    "maitre_ouvrage": "sglaq",
                    "maitre_oeuvre": "",
                    "date_debut_prevue": None,
                    "date_fin_prevue": None,
                    "budget_initial_montant": None,
                    "description": "",
                },
            )
        ],
    )
    def post(self, request):
        serializer = ProjetPostSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        retour = ProjetCreationResponseSerializer(projet)
        return Response(
            retour.data,
            status=status.HTTP_201_CREATED,
            headers={
                "Location": request.build_absolute_uri(
                    reverse("projets:projet-detail", kwargs={"pk": projet.pk})
                )
            },
        )


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
            200: ProjetCreationResponseSerializer,
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
            ProjetCreationResponseSerializer(projet).data,
            status=status.HTTP_200_OK,
        )

    def _modifier(self, request, pk, *, partial):
        projet = get_object_or_404(Projet.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, projet)
        serializer = ProjetPatchSerializer(
            projet, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        return Response(ProjetCreationResponseSerializer(projet).data)

    @extend_schema(
        summary="Modifier partiellement les champs du formulaire",
        tags=["projets"],
        request=ProjetPatchSerializer,
        responses={200: ProjetCreationResponseSerializer},
    )
    @transaction.atomic
    def patch(self, request, pk):
        return self._modifier(request, pk, partial=True)

    @extend_schema(
        summary="Remplacer les informations du formulaire",
        description=(
            "Les quatre champs obligatoires sont requis. "
            "Les facultatifs omis sont reinitialises."
        ),
        tags=["projets"],
        request=ProjetPatchSerializer,
        responses={200: ProjetCreationResponseSerializer},
    )
    @transaction.atomic
    def put(self, request, pk):
        return self._modifier(request, pk, partial=False)

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
