from django.db import transaction
from django.db.models import Exists, OuterRef
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

from apps.core.droits import APermission, peut_voir_montants
from apps.core.permissions import (
    GardePermissionProjet,
    filtrer_queryset_par_affectations,
)
from apps.core.purger_montants import purger_montants_recursif
from apps.projets.models import Element, Projet, ProjetContrat
from apps.projets.selectors.arbre import precharger_arbres
from apps.projets.selectors.configuration import (
    configuration_dynamique_projet,
    dates_reelles_projets_batch,
    tiers_par_nom_batch,
)
from apps.projets.selectors.encadrement import prefetch_encadrement
from apps.projets.serializers.swagger import (
    ContratProjetSerializer,
    ProjetCreationResponseSerializer,
    ProjetPatchSerializer,
    ProjetPostSerializer,
)
from apps.projets.services.affectations import (
    role_par_defaut,
    verifier_peut_gerer_chef_projet,
)
from apps.projets.services.indicateurs_temporels import calendrier_pour_projets
from apps.projets.views.alertes_retard import AlerteRetardListView, AlerteRetardResoudreView
from apps.projets.views.arret_chantier import (
    ArretChantierDetailView,
    ProjetArretChantierListCreateView,
)
from apps.projets.views.calendrier import (
    CalendrierEntrepriseView,
    ExceptionCalendrierDetailView,
    ExceptionCalendrierListCreateView,
    SemaineTypeView,
)
from apps.projets.views.meteo import MeteoProjetView, ReferentielVillesView
from apps.projets.views.planning import ProjetCourbeView, ProjetPlanningView
from apps.projets.views.reprogrammation import (
    ElementHistoriqueDatesView,
    ElementReprogrammerView,
    GlobalJournalReportsView,
    MotifReportListCreateView,
    ProjetHistoriqueDatesView,
    ProjetJournalReportsConsolideView,
    ProjetReprogrammerView,
)
from apps.projets.views.sante import (
    ProjetSanteApercuView,
    ProjetSanteDetailView,
    ProjetSanteHistoriqueView,
)
from apps.projets.views.tableau_de_bord import TableauDeBordView

__all__ = [
    "AlerteRetardListView",
    "AlerteRetardResoudreView",
    "ArretChantierDetailView",
    "CalendrierEntrepriseView",
    "ExceptionCalendrierDetailView",
    "ElementHistoriqueDatesView",
    "ElementReprogrammerView",
    "ExceptionCalendrierListCreateView",
    "GlobalJournalReportsView",
    "MeteoProjetView",
    "MotifReportListCreateView",
    "ProjetArretChantierListCreateView",
    "ProjetConfigurationView",
    "ProjetContratsView",
    "ProjetCourbeView",
    "ProjetDetailView",
    "ProjetHistoriqueDatesView",
    "ProjetJournalReportsConsolideView",
    "ProjetListCreateView",
    "ProjetOrdreServiceView",
    "ProjetPlanningView",
    "ProjetReprogrammerView",
    "ProjetSanteApercuView",
    "ProjetSanteDetailView",
    "ProjetSanteHistoriqueView",
    "ReferentielVillesView",
    "SemaineTypeView",
    "TableauDeBordView",
]



def _queryset_projet_enrichi():
    """Charge un ou plusieurs projets avec encadrement, client et historique des contrats."""
    return Projet.objects.select_related(
        "client",
        "chef_projet",
        "chef_projet__role",
        "conducteur_travaux",
        "conducteur_travaux__role",
        "cree_par",
        "cree_par__role",
    ).prefetch_related("contrats__cree_par", "niveaux", prefetch_encadrement())


class ResultList(list):
    def get(self, key, default=None):
        if key == "results":
            return self
        return default


class ProjetListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/`."""

    parser_classes = [JSONParser, MultiPartParser]

    def get_permissions(self):

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
        qs = _queryset_projet_enrichi().annotate(
            a_un_decoupage=Exists(Element.objects.filter(projet=OuterRef("pk")))
        )
        qs = filtrer_queryset_par_affectations(qs, request.user, champ_projet="id", request=request)
        projets = list(qs)
        precharger_arbres(projets)
        context = {
            "request": request,
            "calendrier": calendrier_pour_projets(projets),
            "premiers_rapports": dates_reelles_projets_batch(projets),
            "tiers_par_nom": tiers_par_nom_batch(projets),
            "detail": False,
        }
        serializer = ProjetCreationResponseSerializer(projets, many=True, context=context)
        return Response(ResultList(serializer.data), status=status.HTTP_200_OK)

    @extend_schema(
        summary="Creer un projet depuis le formulaire Nouveau projet",
        tags=["projets"],
        description=(
            "Nom, categorie d'ouvrage (type_projet), ville et maitre_ouvrage (ou client_id) "
            "sont obligatoires. Maitre_oeuvre, dates, budget et description sont facultatifs. "
            "Reference et duree sont calculees automatiquement. "
            "Statut facultatif, EN_ATTENTE par defaut. "
            "Budget en centimes FCFA. Fin strictement apres debut. "
            "Contrat du marche unique facultatif : envoyer 1 fichier dans multipart/form-data "
            "sous la cle contrat (PDF/JPG/JPEG/PNG, max 10 Mo)."
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

            AffectationProjet.objects.get_or_create(
                projet=projet,
                utilisateur=user,
                defaults={
                    "est_actif": True,
                    "role_projet": role_par_defaut(user),
                    "cree_par": user,
                },
            )

        projet = _queryset_projet_enrichi().get(pk=projet.pk)
        precharger_arbres([projet])
        context = {
            "request": request,
            "calendrier": calendrier_pour_projets([projet]),
            "detail": True,
        }
        retour = ProjetCreationResponseSerializer(projet, context=context)
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
        projet = get_object_or_404(_queryset_projet_enrichi(), pk=pk)
        self.check_object_permissions(request, projet)
        if "ordre_service" in request.query_params:
            if not projet.ordre_service:
                raise NotFound("Ce projet n'a pas d'ordre de service de démarrage.")
            try:
                fichier = projet.ordre_service.open("rb")
            except FileNotFoundError as exc:
                raise NotFound("Le fichier de l'ordre de service est indisponible.") from exc
            response = FileResponse(
                fichier,
                as_attachment=True,
                filename=projet.ordre_service_nom or f"ordre-service-{projet.reference}",
                content_type=projet.ordre_service_type or "application/octet-stream",
            )
            response["Cache-Control"] = "private, no-store"
            return response
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
        # L'arbre sert à plusieurs champs de la réponse : chargé une fois.
        precharger_arbres([projet])
        context = {
            "request": request,
            "calendrier": calendrier_pour_projets([projet]),
            "detail": True,
        }
        return Response(
            ProjetCreationResponseSerializer(projet, context=context).data,
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

        # Le chef de projet est protégé (décision du 22/10/2026) : le retirer ou le remplacer par ce
        # formulaire est réservé à la direction, comme par les routes d'affectation. En PUT, un
        # `chef_projet_id` omis vaut `null` : il retirerait lui aussi le chef de projet.
        # La valeur est lue comme le serializer la lit : `chef_projet_id` d'abord, sinon
        # l'alias `chef_projet` (`ProjetPostSerializer.to_internal_value`).
        if "chef_projet_id" in request.data:
            cle = "chef_projet_id"
        elif "chef_projet" in request.data:
            cle = "chef_projet"
        else:
            cle = None
        if cle is not None or not partial:
            demande = request.data.get(cle) if cle else None
            actuel = projet.chef_projet_id
            if (str(demande) if demande else None) != (str(actuel) if actuel else None):
                verifier_peut_gerer_chef_projet(user, request=request)

        serializer = ProjetPatchSerializer(
            projet, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        projet = serializer.save()
        projet = _queryset_projet_enrichi().get(pk=projet.pk)
        precharger_arbres([projet])
        context = {
            "request": request,
            "calendrier": calendrier_pour_projets([projet]),
            "detail": True,
        }
        return Response(ProjetCreationResponseSerializer(projet, context=context).data)

    @extend_schema(
        summary="Modifier partiellement un projet ou son statut",
        description=(
            "PATCH avec uniquement statut : tout utilisateur authentifie ayant acces "
            "au projet peut changer son etat. EN_COURS reactive le projet. "
            "Les autres modifications exigent le droit d'ecriture du module projets. "
            "Contrat : en multipart, televerser un nouveau contrat remplace le contrat actif "
            "et archive la version precedente dans historique_contrats."
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
            "Les champs obligatoires sont requis. "
            "Les facultatifs omis sont reinitialises. "
            "Le statut omis conserve l'état existant. "
            "Contrat : televerser un nouveau contrat remplace l'actif et archive le precedent."
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


class ProjetOrdreServiceView(APIView):
    """`GET /api/v1/projets/{id}/ordre-service/` — l'ordre de service de démarrage du projet."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        tags=["projets"],
        summary="Télécharger l'ordre de service de démarrage du projet",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        if not projet.ordre_service:
            raise NotFound("Ce projet n'a pas d'ordre de service de démarrage.")
        try:
            fichier = projet.ordre_service.open("rb")
        except FileNotFoundError as exc:
            raise NotFound("Le fichier de l'ordre de service est indisponible.") from exc
        response = FileResponse(
            fichier,
            as_attachment=True,
            filename=projet.ordre_service_nom or f"ordre-service-{projet.reference}",
            content_type=projet.ordre_service_type or "application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ProjetContratsView(APIView):
    """`GET /api/v1/projets/{id}/contrats/` — contrat actif et historique des versions."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        tags=["projets"],
        summary="Consulter le contrat actif et l'historique des versions d'un projet",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.prefetch_related("contrats__cree_par"),
            pk=pk,
        )
        self.check_object_permissions(request, projet)
        contrats = sorted(
            [c for c in projet.contrats.all() if c.supprime_le is None],
            key=lambda c: (-c.version, -(c.cree_le.timestamp() if c.cree_le else 0)),
        )
        actif = next((c for c in contrats if c.est_actif), None) or (
            contrats[0] if contrats else None
        )
        ctx = {"request": request}
        return Response(
            {
                "contrat_actif": (
                    ContratProjetSerializer(actif, context=ctx).data if actif else None
                ),
                "historique_contrats": ContratProjetSerializer(
                    contrats, many=True, context=ctx
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ProjetConfigurationView(APIView):
    """`GET /api/v1/projets/{id}/configuration/` — données dynamiques de configuration/fiche."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        tags=["projets"],
        summary="Données dynamiques de configuration et de fiche projet",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet.objects.select_related("client"), pk=pk)
        self.check_object_permissions(request, projet)
        precharger_arbres([projet])
        montants_visibles = peut_voir_montants(request.user, request)
        donnees = configuration_dynamique_projet(
            projet,
            montants_visibles=montants_visibles,
        )
        if not montants_visibles:
            donnees = purger_montants_recursif(donnees)
        return Response(donnees, status=status.HTTP_200_OK)
