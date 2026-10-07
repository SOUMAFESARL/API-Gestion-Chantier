from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import APermission
from apps.core.permissions import (
    EstDirection,
    GardePermissionProjet,
    filtrer_queryset_par_affectations,
)
from apps.projets.models import Projet, ProjetContrat
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
from apps.projets.views.arret_chantier import (
    ArretChantierDetailView,
    ProjetArretChantierListCreateView,
)
from apps.projets.views.sante import (
    ProjetSanteApercuView,
    ProjetSanteDetailView,
    ProjetSanteHistoriqueView,
)
from apps.projets.views.tableau_de_bord import TableauDeBordView

__all__ = [
    "ActiviteDetailView",
    "ActiviteHistoriqueDatesView",
    "ActiviteReprogrammerView",
    "ArretChantierDetailView",
    "GlobalJournalReportsView",
    "LotActiviteListCreateView",
    "LotHistoriqueDatesView",
    "LotReprogrammerView",
    "MeteoProjetView",
    "MotifReportListCreateView",
    "ProjetArretChantierListCreateView",
    "ProjetDetailView",
    "ProjetHistoriqueDatesView",
    "ProjetJournalReportsConsolideView",
    "ProjetListCreateView",
    "ProjetReprogrammerView",
    "ProjetSanteApercuView",
    "ProjetSanteDetailView",
    "ProjetSanteHistoriqueView",
    "ReferentielVillesView",
    "TableauDeBordView",
]



class ResultList(list):
    def get(self, key, default=None):
        if key == "results":
            return self
        return default


class ProjetListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/`."""

    parser_classes = [JSONParser, MultiPartParser]

    def get_permissions(self):
        from apps.core.droits import APermission

        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                APermission.pour("projets.creer")(),
            ]
        if self.request.method in ("PUT", "PATCH"):
            return [
                IsAuthenticated(),
                APermission.pour("projets.ecrire")(),
            ]
        if self.request.method == "DELETE":
            return [
                IsAuthenticated(),
                APermission.pour("projets.changer_statut")(),
            ]
        return [
            IsAuthenticated(),
            APermission.pour("projets.lire")(),
        ]

    @extend_schema(
        summary="Afficher la liste des projets accessibles",
        tags=["projets"],
        description=(
            "Liste des projets accessibles : champs du formulaire et contrats. "
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
            .prefetch_related("contrats", "lots__activites")
        )
        qs = filtrer_queryset_par_affectations(qs, request.user, champ_projet="id", request=request)
        serializer = ProjetCreationResponseSerializer(qs, many=True, context={"request": request})
        return Response(ResultList(serializer.data), status=status.HTTP_200_OK)

    @extend_schema(
        summary="Creer un projet depuis le formulaire Nouveau projet",
        tags=["projets"],
        description=(
            "Nom, type, ville et maitre_ouvrage sont obligatoires. "
            "Maitre_oeuvre, dates, budget et description sont facultatifs. "
            "Reference et duree sont calculees automatiquement. "
            "Statut facultatif, EN_ATTENTE par defaut. "
            "La reponse expose avancement_reel (pourcentage restant, 100 au depart) "
            "et indice_sante (null sans depenses reelles disponibles). "
            "Budget en centimes FCFA. Fin strictement apres debut. "
            "Les champs hors formulaire sont refuses ; lots et equipe "
            "s'ajoutent ensuite depuis le projet."
            " Contrat facultatif : envoyer les fichiers dans multipart/form-data, "
            "en repetant la cle contrat. Formats PDF/JPG/JPEG/PNG ; JEPG accepte. "
            "Maximum 10 fichiers, 10 Mo chacun et 50 Mo au total."
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
        from apps.billing.services.quota import verifier_quota_avant_projet
        verifier_quota_avant_projet()

        serializer = ProjetPostSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()

        user = request.user
        from apps.core.permissions import obtenir_portee_role

        if user and user.is_authenticated and obtenir_portee_role(user) == "PROJET":
            from apps.projets.models import AffectationProjet

            AffectationProjet.objects.create(
                projet=projet,
                utilisateur=user,
                est_actif=True,
                role_projet="",
                cree_par=user,
            )

        retour = ProjetCreationResponseSerializer(projet, context={"request": request})
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

    parser_classes = [JSONParser, MultiPartParser]

    def get_permissions(self):
        if self.request.method in ("PUT", "DELETE"):
            return [
                IsAuthenticated(),
                GardePermissionProjet.pour("projets.ecrire")(),
            ]
        # Pour GET et PATCH : GardePermissionProjet.pour("projets.lire") vérifie l'accès au chantier,
        # puis _modifier vérifie les permissions fines (ecrire, changer_statut, resilier_archiver).
        return [
            IsAuthenticated(),
            GardePermissionProjet.pour("projets.lire")(),
        ]

    @extend_schema(
        summary="Détail d'un projet",
        parameters=[
            OpenApiParameter(
                "contrat",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                description="UUID d'un contrat du projet a telecharger avec authentification.",
            )
        ],
        tags=["projets"],
        description=(
            "À appeler lorsqu'un utilisateur ouvre un projet depuis la liste. "
            "L'URL du projet est fournie dans l'entete Location lors de sa creation. "
            "La lecture du module et l'accès à ce projet sont contrôlés côté serveur. "
            "La liste contrat contient les liens de telechargement authentifie. "
            "Avec ?contrat=UUID, renvoie le document binaire en piece jointe."
        ),
        responses={
            (200, "application/json"): ProjetCreationResponseSerializer,
            (200, "application/pdf"): OpenApiTypes.BINARY,
            (200, "image/jpeg"): OpenApiTypes.BINARY,
            (200, "image/png"): OpenApiTypes.BINARY,
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.select_related(
                "client", "chef_projet", "conducteur_travaux", "cree_par"
            ).prefetch_related("contrats", "lots__activites"),
            pk=pk,
        )
        self.check_object_permissions(request, projet)
        if "contrat" in request.query_params:
            contrat_id = serializers.UUIDField().run_validation(request.query_params["contrat"])
            document = get_object_or_404(ProjetContrat, pk=contrat_id, projet=projet)
            try:
                fichier = document.fichier.open("rb")
            except FileNotFoundError as exc:
                raise NotFound("Le fichier contrat est indisponible.") from exc
            response = FileResponse(
                fichier,
                as_attachment=True,
                filename=document.nom,
                content_type=document.type_contenu,
            )
            response["Cache-Control"] = "private, no-store"
            return response
        return Response(
            ProjetCreationResponseSerializer(projet, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def _modifier(self, request, pk, *, partial):
        projet = get_object_or_404(Projet.objects.select_for_update(), pk=pk)
        self.check_object_permissions(request, projet)

        from rest_framework.exceptions import PermissionDenied
        from apps.core.droits import a_permission, est_dg
        from apps.projets.services.machine_etats import (
            STATUTS_FIN_DE_VIE,
            verifier_statut_projet_pour_ecriture,
        )

        user = request.user
        nouveau_statut = request.data.get("statut")
        champs = set(request.data.keys())
        champs_autres = champs - {"statut"}

        # Si le projet est déjà clos (fin de vie) et qu'on ne fait pas une réouverture de statut
        if projet.statut in STATUTS_FIN_DE_VIE and not nouveau_statut:
            verifier_statut_projet_pour_ecriture(projet)

        # Si d'autres champs que statut sont modifiés : exige projets.ecrire
        if champs_autres:
            if projet.statut in STATUTS_FIN_DE_VIE:
                verifier_statut_projet_pour_ecriture(projet)
            if not (est_dg(user) or a_permission(user, "projets.ecrire", request=request)):
                raise PermissionDenied("Permission projets.ecrire requise pour modifier les informations du projet.")

        # Si le statut est modifié
        if nouveau_statut:
            # Fin de vie ou sortie de fin de vie : exige projets.resilier_archiver (DG, AD, DO)
            if nouveau_statut in STATUTS_FIN_DE_VIE or projet.statut in STATUTS_FIN_DE_VIE:
                if not (est_dg(user) or a_permission(user, "projets.resilier_archiver", request=request)):
                    raise PermissionDenied("Permission projets.resilier_archiver requise pour résilier, archiver, désactiver ou réactiver un chantier.")
            else:
                # Statuts opérationnels : exige projets.changer_statut (DG, AD, DO, CP)
                if not (est_dg(user) or a_permission(user, "projets.changer_statut", request=request)):
                    raise PermissionDenied("Permission projets.changer_statut requise pour modifier le statut du chantier.")
        elif not champs_autres:
            if not (est_dg(user) or a_permission(user, "projets.ecrire", request=request)):
                raise PermissionDenied("Permission projets.ecrire requise.")

        serializer = ProjetPatchSerializer(
            projet, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        return Response(ProjetCreationResponseSerializer(projet, context={"request": request}).data)

    @extend_schema(
        summary="Modifier partiellement un projet ou son statut",
        description=(
            "PATCH avec uniquement statut : tout utilisateur authentifie ayant acces "
            "au projet peut changer son etat. EN_COURS reactive le projet. "
            "Les etats n'interdisent pas les operations. Les autres modifications "
            "exigent toujours le droit d'ecriture du module projets. "
            "Contrat : en multipart, les nouveaux fichiers s'ajoutent aux contrats existants."
        ),
        tags=["projets"],
        request=ProjetPatchSerializer,
        responses={
            200: ProjetCreationResponseSerializer,
            400: OpenApiResponse(description="Statut inconnu ou champs invalides."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(
                description=(
                    "Accès au projet refusé ou droit d'écriture requis pour les autres champs."
                )
            ),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
        examples=[
            OpenApiExample(label, request_only=True, value={"statut": value})
            for label, value in (
                ("Mettre en attente", "EN_ATTENTE"),
                ("Suspendre le projet", "SUSPENDU"),
                ("Bloquer le projet", "BLOQUE"),
                ("Désactiver le projet", "DESACTIVE"),
                ("Résilier le projet", "RESILIE"),
                ("Réactiver le projet", "EN_COURS"),
            )
        ],
    )
    @transaction.atomic
    def patch(self, request, pk):
        return self._modifier(request, pk, partial=True)

    @extend_schema(
        summary="Remplacer les informations du formulaire",
        description=(
            "Les quatre champs obligatoires sont requis. "
            "Les facultatifs omis sont reinitialises."
            " Le statut omis conserve l'état existant."
            " Contrat : les nouveaux fichiers s'ajoutent ; les contrats existants sont conserves."
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
