"""Vues pour la reprogrammation de dates et l'historique (US-033, RG-11).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.db import models
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, RoleGlobal
from apps.core.droits import APermission
from apps.core.pagination import PaginationStandard
from apps.core.permissions import GardePermissionProjet
from apps.projets.models import (
    Element,
    HistoriqueDate,
    MotifReport,
    Projet,
    TypeObjetHistorique,
)
from apps.projets.serializers import (
    HistoriqueDateSerializer,
    MotifReportCreationSerializer,
    MotifReportSerializer,
    ReprogrammationRequestSerializer,
    ReprogrammationResponseSerializer,
)
from apps.projets.services.reprogrammation import reprogrammer_date_instance

__all__ = [
    "ElementHistoriqueDatesView",
    "ElementReprogrammerView",
    "GlobalJournalReportsView",
    "MotifReportListCreateView",
    "ProjetHistoriqueDatesView",
    "ProjetJournalReportsConsolideView",
    "ProjetReprogrammerView",
]



class MotifReportListCreateView(APIView):
    """Liste et création dynamique des motifs de report de dates."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        return [IsAuthenticated(), APermission.pour("pilotage.lire")()]

    @extend_schema(
        summary="Lister les motifs de report actifs",
        tags=["reprogrammation"],
        responses={200: MotifReportSerializer(many=True)},
    )
    def get(self, request):
        motifs = MotifReport.objects.filter(supprime_le__isnull=True, est_actif=True)
        return Response(MotifReportSerializer(motifs, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer un nouveau motif dynamique de report",
        tags=["reprogrammation"],
        request=MotifReportCreationSerializer,
        responses={
            201: MotifReportSerializer,
            400: OpenApiResponse(description="Données invalides ou code en doublon."),
        },
    )
    def post(self, request):
        serializer = MotifReportCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        motif = serializer.save(cree_par=request.user)
        return Response(MotifReportSerializer(motif).data, status=status.HTTP_201_CREATED)


class BaseReprogrammerView(APIView):
    """Classe de base pour les actions de reprogrammation de dates."""

    parser_classes = [JSONParser]
    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.ecrire"),
    ]

    def executer_reprogrammation(self, request, instance, type_objet: str):
        self.check_object_permissions(request, instance)

        projet = instance if type_objet == TypeObjetHistorique.PROJET else instance.projet
        if projet:
            from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

            verifier_statut_projet_pour_ecriture(projet, action="REPROGRAMMATION")

        serializer = ReprogrammationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        from apps.projets.services.perimetres import exiger, peut

        element = instance if type_objet == TypeObjetHistorique.ELEMENT else None
        exiger(request.user, "projets.planifier", projet, element, request=request)
        if type_objet == TypeObjetHistorique.PROJET:
            # Prolonger le projet exige `projets.prolonger` (§11.2) ; l'avancer, `planifier`.
            if data["date_fin_prevue"] > (projet.date_fin_prevue or data["date_fin_prevue"]):
                exiger(request.user, "projets.prolonger", projet, request=request)
        resultat = reprogrammer_date_instance(
            instance=instance,
            nouvelle_date_fin=data["date_fin_prevue"],
            nouvelle_date_debut=data.get("date_debut_prevue"),
            motif_id=str(data["motif_id"]),
            justification=data["justification"],
            auteur=request.user,
            prolonger=data.get("prolonger", False),
            autorise_a_prolonger=peut(request.user, "projets.prolonger", projet, element, request),
        )

        resultat["type_objet"] = type_objet
        rep_serializer = ReprogrammationResponseSerializer(resultat)
        return Response(rep_serializer.data, status=status.HTTP_200_OK)


class ProjetReprogrammerView(BaseReprogrammerView):
    """Reprogrammation de la date prévisionnelle d'un Projet (US-033)."""

    @extend_schema(
        summary="Reprogrammer les dates prévisionnelles d'un projet",
        tags=["reprogrammation"],
        request=ReprogrammationRequestSerializer,
        responses={
            200: ReprogrammationResponseSerializer,
            400: OpenApiResponse(description="Justification < 30 car., motif invalide ou dépassement."),
            403: OpenApiResponse(description="Accès non autorisé au projet."),
            404: OpenApiResponse(description="Projet introuvable."),
        },
    )
    def post(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        return self.executer_reprogrammation(request, projet, TypeObjetHistorique.PROJET)


class ElementReprogrammerView(BaseReprogrammerView):
    """Reprogrammation des dates prévisionnelles d'une case de l'arbre (§11).

    Le parent encadre : on ne resserre pas une case en deçà de ses enfants. Des dates qui
    débordent du parent répondent `prolongation_requise` avec la liste des cases à prolonger ;
    `prolonger: true` confirme. Prolonger le projet ou une case commencée exige
    `projets.prolonger`.
    """

    @extend_schema(
        summary="Reprogrammer les dates prévisionnelles d'une case",
        tags=["reprogrammation"],
        request=ReprogrammationRequestSerializer,
        responses={
            200: ReprogrammationResponseSerializer,
            400: OpenApiResponse(description="Justification < 30 car., motif invalide."),
            403: OpenApiResponse(description="Hors périmètre, ou prolongation non autorisée."),
            404: OpenApiResponse(description="Case introuvable."),
            422: OpenApiResponse(description="`prolongation_requise` : confirmer la prolongation."),
        },
    )
    def post(self, request, pk):
        element = get_object_or_404(Element.objects.select_related("projet"), pk=pk)
        return self.executer_reprogrammation(request, element, TypeObjetHistorique.ELEMENT)


class BaseHistoriqueDatesView(APIView):
    """Consultation de la traçabilité des dates (HistoriqueDate)."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    def lister_historique(self, request, instance, filtre_kwargs):
        self.check_object_permissions(request, instance)
        historiques = (
            HistoriqueDate.objects.filter(**filtre_kwargs)
            .select_related("motif", "auteur")
            .order_by("-cree_le")
        )
        return Response(HistoriqueDateSerializer(historiques, many=True).data, status=status.HTTP_200_OK)


class ProjetHistoriqueDatesView(BaseHistoriqueDatesView):
    """Historique des décalages d'un projet."""

    @extend_schema(
        summary="Consulter l'historique des dates d'un projet",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        return self.lister_historique(
            request,
            projet,
            {"projet": projet, "type_objet": TypeObjetHistorique.PROJET},
        )


class ElementHistoriqueDatesView(BaseHistoriqueDatesView):
    """Historique des décalages d'une case de l'arbre."""

    @extend_schema(
        summary="Consulter l'historique des dates d'une case",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request, pk):
        element = get_object_or_404(Element.objects.select_related("projet"), pk=pk)
        return self.lister_historique(
            request,
            element,
            {"element": element, "type_objet": TypeObjetHistorique.ELEMENT},
        )


class JournalReportsFiltreMixin:
    """Mixin pour filtrer le journal d'audit des reports."""

    def appliquer_filtres(self, qs, params):
        motif_id = params.get("motif_id")
        if motif_id:
            qs = qs.filter(motif_id=motif_id)

        auteur_id = params.get("auteur_id")
        if auteur_id:
            qs = qs.filter(auteur_id=auteur_id)

        type_objet = params.get("type_objet")
        if type_objet:
            qs = qs.filter(type_objet=type_objet.upper())

        champ = params.get("champ")
        if champ:
            qs = qs.filter(champ=champ)

        ecart_min = params.get("ecart_min")
        if ecart_min is not None and ecart_min != "":
            try:
                qs = qs.filter(ecart_jours__gte=int(ecart_min))
            except ValueError:
                pass

        ecart_max = params.get("ecart_max")
        if ecart_max is not None and ecart_max != "":
            try:
                qs = qs.filter(ecart_jours__lte=int(ecart_max))
            except ValueError:
                pass

        date_debut = params.get("date_debut")
        if date_debut:
            qs = qs.filter(cree_le__date__gte=date_debut)

        date_fin = params.get("date_fin")
        if date_fin:
            qs = qs.filter(cree_le__date__lte=date_fin)

        return qs


class ProjetJournalReportsConsolideView(APIView, JournalReportsFiltreMixin):
    """Journal consolidé des reports d'un chantier : le projet et les cases de son arbre."""

    pagination_class = PaginationStandard
    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        operation_id="projets_journal_reports_consolide_list",
        summary="Journal d'audit consolidé des reports d'un chantier",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)

        qs = (
            HistoriqueDate.objects.filter(
                models.Q(projet=projet)
                | models.Q(element__projet=projet)
            )
            .select_related("motif", "auteur", "projet", "element", "element__projet")
            .order_by("-cree_le")
        )
        qs = self.appliquer_filtres(qs, request.query_params)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = HistoriqueDateSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = HistoriqueDateSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GlobalJournalReportsView(APIView, JournalReportsFiltreMixin):
    """Journal d'audit global des reports pour la Direction Générale et l'Admin Tenant."""

    pagination_class = PaginationStandard
    permission_classes = [
        IsAuthenticated,
        APermission.pour("projets.lire"),
    ]

    @extend_schema(
        operation_id="projets_global_journal_reports_list",
        summary="Journal d'audit global des reports de dates (multi-chantiers)",
        tags=["reprogrammation"],
        responses={200: HistoriqueDateSerializer(many=True)},
    )
    def get(self, request):
        qs = (
            HistoriqueDate.objects.all()
            .select_related("motif", "auteur", "projet", "element", "element__projet")
            .order_by("-cree_le")
        )

        # Règle D-06 : filtrage par les projets accessibles
        from apps.core.permissions import obtenir_portee_role, obtenir_projets_ids_actifs_utilisateur
        from apps.core.droits import est_dg

        user = request.user
        if not (user.is_superuser or est_dg(user) or obtenir_portee_role(user) == "ENTREPRISE"):
            projets_ids = obtenir_projets_ids_actifs_utilisateur(user, request=request)
            qs = qs.filter(
                models.Q(projet_id__in=projets_ids)
                | models.Q(element__projet_id__in=projets_ids)
            )

        projet_id = request.query_params.get("projet_id")
        if projet_id:
            qs = qs.filter(
                models.Q(projet_id=projet_id)
                | models.Q(element__projet_id=projet_id)
            )

        qs = self.appliquer_filtres(qs, request.query_params)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = HistoriqueDateSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = HistoriqueDateSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

