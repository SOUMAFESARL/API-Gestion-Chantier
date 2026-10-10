"""Suppression définitive d'une entreprise cliente — aperçu, puis suppression."""

from django.conf import settings
from django.shortcuts import get_object_or_404
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.views.parametres import _exiger_superviseur
from apps.tenants.models import Entreprise
from apps.tenants.services.suppression_definitive import (
    apercu_suppression,
    est_protegee,
    supprimer_definitivement,
)


def _erreur(request, code: str, message: str, statut: int) -> Response:
    return Response(
        {
            "erreur": {
                "code": code,
                "message": message,
                "details": {},
                "trace_id": getattr(request, "identifiant_requete", None),
            }
        },
        status=statut,
    )


def _entreprise_cliente(client_id) -> Entreprise:
    return get_object_or_404(
        Entreprise.objects.exclude(schema_name=get_public_schema_name()), pk=client_id
    )


class ApercuSuppressionClientView(APIView):
    """`GET /api/v1/admins/clients/{id}/suppression/apercu/` — ce que la suppression emporterait."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    def get(self, request, client_id):
        entreprise = _entreprise_cliente(client_id)
        donnees = apercu_suppression(entreprise)
        donnees["suppression_activee"] = bool(settings.SUPPRESSION_ENTREPRISE_ACTIVEE)
        return Response(donnees, status=status.HTTP_200_OK)


class SupprimerClientDefinitivementView(APIView):
    """`POST /api/v1/admins/clients/{id}/supprimer-definitivement/` — corps : `{"confirmation": "<slug>"}`.

    Réservé au superviseur, désactivé par défaut (`SUPPRESSION_ENTREPRISE_ACTIVEE`), jamais sur
    `public` ni `demo`. Il faut retaper le nom technique de l'entreprise.
    """

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    def post(self, request, client_id):
        _exiger_superviseur(request)
        entreprise = _entreprise_cliente(client_id)

        if est_protegee(entreprise):
            return _erreur(request, "entreprise_protegee",
                           "Cette entreprise est protégée : elle ne peut pas être supprimée.", 403)
        if not settings.SUPPRESSION_ENTREPRISE_ACTIVEE:
            return _erreur(request, "suppression_desactivee",
                           "La suppression définitive est désactivée sur ce serveur.", 403)
        saisie = str(request.data.get("confirmation", "")).strip().lower()
        if saisie != entreprise.schema_name.lower():
            return _erreur(request, "confirmation_invalide",
                           "Le nom saisi ne correspond pas à celui de l'entreprise.", 400)

        identifiant, schema, raison = str(entreprise.id), entreprise.schema_name, entreprise.raison_sociale
        rapport = supprimer_definitivement(entreprise)

        with schema_context(get_public_schema_name()):
            JournalPlateforme.objects.create(
                utilisateur_id=request.user.id,
                entreprise_id=entreprise.id,
                action="SUPPRESSION_DEFINITIVE_ENTREPRISE",
                detail={
                    "schema": schema,
                    "raison_sociale": raison,
                    "nb_utilisateurs": rapport["nb_utilisateurs"],
                    "nb_projets": rapport["nb_projets"],
                    "nb_adresses_liberees": len(rapport["adresses_liberees"]),
                },
                adresse_ip=extraire_ip_client(request),
                appareil=request.headers.get("User-Agent", "")[:255],
            )
        return Response(
            {"statut": "supprimee", "id": identifiant, "slug": schema, **rapport},
            status=status.HTTP_200_OK,
        )
