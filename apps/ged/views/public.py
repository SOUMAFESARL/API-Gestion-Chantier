"""Vues publiques anonymes de consultation/téléchargement d'un document partagé 72 h (tâche 3.9).

Aucun JWT n'est requis (`AllowAny`, `authentication_classes = []`). L'isolation D9 est
assurée par `ouvrir_partage_public(jeton)` (lookup exact en portée plateforme suivi d'une
bascule immédiate dans `contexte_entreprise`).
"""

from __future__ import annotations

from django.http import FileResponse
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ged.serializers.partages import DocumentPartagePublicSerializer
from apps.ged.services.partages import (
    enregistrer_telechargement_partage_public,
    ouvrir_partage_public,
)

__all__ = [
    "PartagePublicDetailView",
    "PartagePublicTelechargerView",
]

TAGS = ["ged-public"]


class PartagePublicDetailView(APIView):
    """`GET /api/v1/public/partages/{jeton}/` — métadonnées publiques sans compte."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "partage_public"

    @extend_schema(
        tags=TAGS,
        auth=[],
        summary="Consulter les métadonnées publiques d'un document partagé (72 h)",
        responses={
            200: DocumentPartagePublicSerializer,
            404: OpenApiResponse(description="Jeton de partage inconnu."),
            410: OpenApiResponse(description="Lien expiré, révoqué ou document retiré."),
        },
    )
    def get(self, request, jeton):
        with ouvrir_partage_public(jeton) as (partage, document, version_active):
            payload = {
                "jeton": partage.jeton,
                "expire_le": partage.expire_le,
                "destinataire": partage.destinataire,
                "note": partage.note,
                "entreprise_nom": document.entreprise.raison_sociale,
                "projet_nom": document.projet.nom,
                "projet_reference": document.projet.reference,
                "document": {
                    "nom": document.nom,
                    "categorie": document.categorie,
                    "description": document.description,
                    "version": version_active.numero,
                    "nom_fichier": version_active.nom_fichier_affiche,
                    "taille": version_active.taille,
                    "mime_type": version_active.mime_type,
                    "hash_sha256": version_active.hash_sha256,
                    "depose_le": version_active.cree_le,
                },
            }
        return Response(
            DocumentPartagePublicSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


class PartagePublicTelechargerView(APIView):
    """`GET /api/v1/public/partages/{jeton}/telecharger/` — téléchargement public anonyme."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "partage_public"

    @extend_schema(
        tags=TAGS,
        auth=[],
        summary="Télécharger la version active d'un document partagé (72 h, sans compte)",
        responses={
            (200, "application/octet-stream"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="Jeton de partage inconnu."),
            410: OpenApiResponse(description="Lien expiré, révoqué ou document retiré."),
        },
    )
    def get(self, request, jeton):
        with ouvrir_partage_public(jeton) as (partage, document, version_active):
            try:
                flux = version_active.fichier.open("rb")
            except FileNotFoundError as exc:
                raise NotFound(_("Le fichier partagé est introuvable sur le stockage.")) from exc

            enregistrer_telechargement_partage_public(
                partage=partage,
                document=document,
                version=version_active,
                request=request,
            )
            nom_fichier = (
                version_active.nom_fichier_affiche
                or f"{document.nom}_{version_active.numero}"
            )
            mime_type = version_active.mime_type or "application/octet-stream"

        reponse = FileResponse(
            flux,
            as_attachment=True,
            filename=nom_fichier,
            content_type=mime_type,
        )
        reponse["Cache-Control"] = "private, no-store"
        return reponse
