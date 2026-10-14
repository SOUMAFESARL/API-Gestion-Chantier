"""Suppression définitive d'une entreprise cliente — aperçu, puis suppression."""

import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.emails import envoyer
from apps.core.enums import StatutEntreprise
from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.permissions import EstSuperAdminPlateforme, exiger_superviseur
from apps.platform_admin.services.notifications import (
    SUJET_SUPPRESSION_ENTREPRISE,
    trouver_dg_actif_entreprise,
)
from apps.tenants.models import Entreprise
from apps.tenants.services.sauvegarde_schema import (
    SauvegardeImpossible,
    sauvegarder_schema,
)
from apps.tenants.services.suppression_definitive import (
    apercu_suppression,
    est_protegee,
    supprimer_definitivement,
)

logger = logging.getLogger(__name__)

MOTIF_LONGUEUR_MIN = 20


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


def _prevenir_dg_avant_suppression(entreprise: Entreprise) -> None:
    """Le DG apprend la suppression avant qu'elle ait lieu — sans le motif, interne à l'éditeur."""
    dg = trouver_dg_actif_entreprise(entreprise)
    if not dg or not dg.email:
        logger.info("Suppression de %s : aucun DG actif à prévenir.", entreprise.schema_name)
        return
    message = (
        "Bonjour,\n\n"
        f"L'espace de {entreprise.raison_sociale} sur CCD Digital va être supprimé "
        "définitivement par l'administration de la plateforme. Les comptes de vos "
        "collaborateurs et les données de vos projets ne seront plus accessibles.\n\n"
        "Pour toute question, répondez à ce courriel."
    )
    envoye = envoyer(
        "notification_plateforme",
        SUJET_SUPPRESSION_ENTREPRISE,
        dg.email,
        {
            "sujet": SUJET_SUPPRESSION_ENTREPRISE,
            "message": message,
            "raison_sociale": entreprise.raison_sociale,
        },
    )
    if not envoye:
        logger.error(
            "Suppression de %s : le courriel au DG n'est pas parti.",
            entreprise.schema_name,
        )


class ApercuSuppressionClientView(APIView):
    """`GET /api/v1/admins/clients/{id}/suppression/apercu/` — ce que la suppression emporterait."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    def get(self, request, client_id):
        entreprise = _entreprise_cliente(client_id)
        donnees = apercu_suppression(entreprise)
        donnees["suppression_activee"] = bool(settings.SUPPRESSION_ENTREPRISE_ACTIVEE)
        donnees["suspendue"] = entreprise.statut == StatutEntreprise.SUSPENDU
        donnees["motif_longueur_min"] = MOTIF_LONGUEUR_MIN
        donnees["sauvegarde_conservee_jours"] = getattr(
            settings, "SAUVEGARDES_SUPPRESSION_JOURS", 30
        )
        return Response(donnees, status=status.HTTP_200_OK)


class SupprimerClientDefinitivementView(APIView):
    """`POST /api/v1/admins/clients/{id}/supprimer-definitivement/` —
    corps : `{"confirmation": "<slug>", "motif": "..."}`.

    Contrôles dans l'ordre strict :
    1. exiger_superviseur
    2. _entreprise_cliente (404)
    3. est_protegee (403)
    4. SUPPRESSION_ENTREPRISE_ACTIVEE (403)
    5. entreprise suspendue (409)
    6. motif >= 20 caractères (400)
    7. confirmation == slug (400)
    8. sauvegarde du schéma (503)
    """

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    def post(self, request, client_id):
        exiger_superviseur(request)
        entreprise = _entreprise_cliente(client_id)

        # 3. Entreprise protégée (public, demo)
        if est_protegee(entreprise):
            return _erreur(
                request,
                "entreprise_protegee",
                "Cette entreprise est protégée : elle ne peut pas être supprimée.",
                status.HTTP_403_FORBIDDEN,
            )

        # 4. Interrupteur de suppression désactivé
        if not settings.SUPPRESSION_ENTREPRISE_ACTIVEE:
            return _erreur(
                request,
                "suppression_desactivee",
                "La suppression définitive est désactivée sur ce serveur.",
                status.HTTP_403_FORBIDDEN,
            )

        # 5. Entreprise non suspendue
        if entreprise.statut != StatutEntreprise.SUSPENDU:
            return _erreur(
                request,
                "entreprise_non_suspendue",
                "Suspendez d'abord l'entreprise : "
                "seule une entreprise suspendue peut être supprimée.",
                status.HTTP_409_CONFLICT,
            )

        # 6. Motif >= 20 caractères
        motif = str(request.data.get("motif", "")).strip()
        if len(motif) < MOTIF_LONGUEUR_MIN:
            return _erreur(
                request,
                "motif_invalide",
                "Le motif doit contenir au moins 20 caractères.",
                status.HTTP_400_BAD_REQUEST,
            )

        # 7. Confirmation égale au nom technique (slug)
        saisie = str(request.data.get("confirmation", "")).strip().lower()
        if saisie != entreprise.schema_name.lower():
            return _erreur(
                request,
                "confirmation_invalide",
                "Le nom saisi ne correspond pas à celui de l'entreprise.",
                status.HTTP_400_BAD_REQUEST,
            )

        # 8. Sauvegarde du schéma
        apercu = apercu_suppression(entreprise)
        try:
            sauvegarde = sauvegarder_schema(entreprise, complement=apercu)
        except SauvegardeImpossible:
            return _erreur(
                request,
                "sauvegarde_impossible",
                "La sauvegarde de l'entreprise a échoué : la suppression n'a pas été faite. "
                "Prévenez l'équipe technique.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Notification au DG avant suppression du schéma
        _prevenir_dg_avant_suppression(entreprise)

        identifiant = str(entreprise.id)
        schema = entreprise.schema_name
        raison = entreprise.raison_sociale

        rapport = supprimer_definitivement(entreprise)

        with schema_context(get_public_schema_name()):
            JournalPlateforme.objects.create(
                utilisateur_id=request.user.id,
                entreprise_id=entreprise.id,
                action="SUPPRESSION_DEFINITIVE_ENTREPRISE",
                detail={
                    "schema": schema,
                    "raison_sociale": raison,
                    "motif": motif,
                    "sauvegarde": sauvegarde.name,
                    "nb_utilisateurs": rapport["nb_utilisateurs"],
                    "nb_projets": rapport["nb_projets"],
                    "nb_adresses_liberees": len(rapport["adresses_liberees"]),
                },
                adresse_ip=extraire_ip_client(request),
                appareil=request.headers.get("User-Agent", "")[:255],
            )

        return Response(
            {
                "statut": "supprimee",
                "id": identifiant,
                "slug": schema,
                "sauvegarde": sauvegarde.name,
                **rapport,
            },
            status=status.HTTP_200_OK,
        )
