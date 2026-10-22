"""Vues API pour le calendrier d'entreprise (SFD F3 §6 & Erratum E-4).

Routes :
- GET /api/v1/calendrier/ : consultation de la semaine type, jours fériés nationaux et exceptions
- PATCH /api/v1/calendrier/semaine-type/ : modification de la semaine type
- POST /api/v1/calendrier/exceptions/ : création d'une exception
- DELETE /api/v1/calendrier/exceptions/{id}/ : suppression logique d'une exception
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.core.droits import APermission
from apps.core.enums import ActionAudit
from apps.core.exceptions import ErreurConflit
from apps.core.ip_restriction import extraire_ip_client
from apps.projets.models.calendrier import ExceptionCalendrier, SemaineType
from apps.projets.serializers.calendrier import (
    CalendrierQuerySerializer,
    CalendrierResponseSerializer,
    ExceptionCalendrierCreateSerializer,
    ExceptionCalendrierResponseSerializer,
    SemaineTypeSerializer,
    SemaineTypeUpdateSerializer,
)
from apps.referentiels.models import JourFerie

__all__ = [
    "CalendrierEntrepriseView",
    "ExceptionCalendrierDetailView",
    "ExceptionCalendrierListCreateView",
    "SemaineTypeView",
]


class CalendrierEntrepriseView(APIView):
    """`GET /api/v1/calendrier/` — Consultation du calendrier de l'entreprise."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Consulter le calendrier d'entreprise",
        description=(
            "Renvoie la semaine type, les jours fériés nationaux et les exceptions "
            "d'entreprise sur la période demandée (par défaut, l'année civile en cours). "
            "La période ne peut pas dépasser 366 jours."
        ),
        parameters=[
            OpenApiParameter(
                name="debut",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Date de début au format AAAA-MM-JJ "
                    "(par défaut, 1er janvier de l'année en cours)."
                ),
            ),
            OpenApiParameter(
                name="fin",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Date de fin au format AAAA-MM-JJ "
                    "(par défaut, 31 décembre de l'année en cours)."
                ),
            ),
        ],
        responses={
            200: CalendrierResponseSerializer,
            400: OpenApiResponse(description="Période invalide ou supérieure à 366 jours."),
        },
        tags=["calendrier"],
    )
    def get(self, request):
        query_serializer = CalendrierQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        debut = query_serializer.validated_data["debut"]
        fin = query_serializer.validated_data["fin"]

        semaine = SemaineType.courante()
        semaine_data = SemaineTypeSerializer(semaine).data

        with schema_context(get_public_schema_name()):
            feries_qs = JourFerie.objects.filter(
                pays="CI",
                date_ferie__gte=debut,
                date_ferie__lte=fin,
            ).order_by("date_ferie")
            feries_nationaux = [
                {"date": jf.date_ferie.isoformat(), "libelle": jf.libelle}
                for jf in feries_qs
            ]

        exceptions_qs = ExceptionCalendrier.objects.filter(
            supprime_le__isnull=True,
            date__gte=debut,
            date__lte=fin,
        ).order_by("date")
        exceptions_data = ExceptionCalendrierResponseSerializer(exceptions_qs, many=True).data

        return Response(
            {
                "semaine_type": semaine_data,
                "feries_nationaux": feries_nationaux,
                "exceptions": exceptions_data,
            },
            status=status.HTTP_200_OK,
        )


class SemaineTypeView(APIView):
    """`PATCH /api/v1/calendrier/semaine-type/` — Modification de la semaine type."""

    parser_classes = [JSONParser]
    permission_classes = [
        IsAuthenticated,
        APermission.pour("administration.calendrier_gerer"),
    ]

    @extend_schema(
        summary="Modifier la semaine type de travail",
        description=(
            "Modifie un ou plusieurs des sept jours de la semaine travaillés. "
            "Une semaine sans aucun jour travaillé est refusée (ErreurMetier, 422). "
            "Exige la permission administration.calendrier_gerer (DG, AD)."
        ),
        request=SemaineTypeUpdateSerializer,
        responses={
            200: SemaineTypeSerializer,
            400: OpenApiResponse(description="Données invalides."),
            403: OpenApiResponse(description="Permission non accordée."),
            422: OpenApiResponse(description="Semaine sans aucun jour travaillé."),
        },
        tags=["calendrier"],
    )
    def patch(self, request):
        semaine = SemaineType.courante()
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        valeur_avant = {j: getattr(semaine, j) for j in jours}

        serializer = SemaineTypeUpdateSerializer(
            instance=semaine,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        valeurs_apres = {
            j: serializer.validated_data.get(j, getattr(semaine, j))
            for j in jours
        }

        for j, v in serializer.validated_data.items():
            setattr(semaine, j, v)
        semaine.save(update_fields=[*serializer.validated_data, "modifie_le"])

        appareil = (
            request.headers.get("User-Agent")
            or request.META.get("HTTP_USER_AGENT", "")
            or ""
        )[:255]
        journaliser(
            action=ActionAudit.MODIFICATION,
            type_entite="semaine_type",
            entite_id=semaine.pk,
            utilisateur_id=request.user.pk,
            valeur_avant=valeur_avant,
            valeur_apres=valeurs_apres,
            adresse_ip=extraire_ip_client(request) or None,
            appareil=appareil,
        )

        return Response(SemaineTypeSerializer(semaine).data, status=status.HTTP_200_OK)


class ExceptionCalendrierListCreateView(APIView):
    """`POST /api/v1/calendrier/exceptions/` — Création d'une exception."""

    parser_classes = [JSONParser]
    permission_classes = [
        IsAuthenticated,
        APermission.pour("administration.calendrier_gerer"),
    ]

    @extend_schema(
        summary="Créer une exception de calendrier",
        description=(
            "Crée une exception de calendrier (date précise, jour ouvré ou non, motif). "
            "Une date ayant déjà une exception active est refusée en 409 (ErreurConflit). "
            "Exige la permission administration.calendrier_gerer (DG, AD)."
        ),
        request=ExceptionCalendrierCreateSerializer,
        responses={
            201: ExceptionCalendrierResponseSerializer,
            400: OpenApiResponse(description="Champs manquants ou invalides."),
            403: OpenApiResponse(description="Permission non accordée."),
            409: OpenApiResponse(
                description="Une exception active existe déjà pour cette date."
            ),
        },
        tags=["calendrier"],
    )
    def post(self, request):
        serializer = ExceptionCalendrierCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                exception = serializer.save(cree_par=request.user)
        except IntegrityError as exc:
            raise ErreurConflit("Une exception active existe déjà pour cette date.") from exc

        appareil = (
            request.headers.get("User-Agent")
            or request.META.get("HTTP_USER_AGENT", "")
            or ""
        )[:255]
        journaliser(
            action=ActionAudit.CREATION,
            type_entite="exception_calendrier",
            entite_id=exception.pk,
            utilisateur_id=request.user.pk,
            valeur_avant=None,
            valeur_apres={
                "id": str(exception.pk),
                "date": exception.date.isoformat(),
                "ouvre": exception.ouvre,
                "motif": exception.motif,
            },
            adresse_ip=extraire_ip_client(request) or None,
            appareil=appareil,
        )

        return Response(
            ExceptionCalendrierResponseSerializer(exception).data,
            status=status.HTTP_201_CREATED,
        )


class ExceptionCalendrierDetailView(APIView):
    """`DELETE /api/v1/calendrier/exceptions/{id}/` — Suppression logique d'une exception."""

    permission_classes = [
        IsAuthenticated,
        APermission.pour("administration.calendrier_gerer"),
    ]

    @extend_schema(
        summary="Supprimer logiquement une exception de calendrier",
        description=(
            "Supprime logiquement une exception de calendrier. Jamais de suppression physique. "
            "Exige la permission administration.calendrier_gerer (DG, AD)."
        ),
        responses={
            204: None,
            403: OpenApiResponse(description="Permission non accordée."),
            404: OpenApiResponse(description="Exception introuvable ou déjà supprimée."),
        },
        tags=["calendrier"],
    )
    def delete(self, request, pk):
        exception = get_object_or_404(
            ExceptionCalendrier,
            pk=pk,
            supprime_le__isnull=True,
        )

        valeur_avant = {
            "id": str(exception.pk),
            "date": exception.date.isoformat(),
            "ouvre": exception.ouvre,
            "motif": exception.motif,
        }

        exception.delete(utilisateur=request.user)

        appareil = (
            request.headers.get("User-Agent")
            or request.META.get("HTTP_USER_AGENT", "")
            or ""
        )[:255]
        journaliser(
            action=ActionAudit.SUPPRESSION,
            type_entite="exception_calendrier",
            entite_id=exception.pk,
            utilisateur_id=request.user.pk,
            valeur_avant=valeur_avant,
            valeur_apres={"supprime": True},
            adresse_ip=extraire_ip_client(request) or None,
            appareil=appareil,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)
