"""Vues pour les activités de travaux (MLD §6.3).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Activite, Lot, Projet
from apps.projets.serializers import (
    ActiviteCreationSerializer,
    ActiviteModificationSerializer,
    ActiviteSerializer,
)
from apps.projets.serializers.lot import ActivationSerializer


__all__ = ["ActiviteDetailView", "LotActiviteListCreateView"]

ERREURS_ACTIVITES = {
    401: OpenApiResponse(description="Authentification requise."),
    403: OpenApiResponse(description="Accès au projet parent refusé."),
    404: OpenApiResponse(description="Lot ou activité absent ou supprimé."),
    400: OpenApiResponse(description="Champs invalides, dépendance ou état du lot incompatible."),
}


class LotActiviteListCreateView(APIView):
    """Liste et création des activités pour un lot donné."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), GardePermissionProjet.pour("projets.ecrire")()]
        return [IsAuthenticated(), GardePermissionProjet.pour("projets.lire")()]

    @extend_schema(
        summary="Lister les activités d'un lot",
        tags=["activités"],
        responses={200: ActiviteSerializer(many=True), **ERREURS_ACTIVITES},
    )
    def get(self, request, lot_id):
        lot = get_object_or_404(
            Lot.objects.select_related("projet").filter(projet__supprime_le__isnull=True), pk=lot_id
        )
        self.check_object_permissions(request, lot)
        activites = lot.activites.filter(supprime_le__isnull=True).order_by("ordre", "cree_le")
        return Response(
            ActiviteSerializer(activites.prefetch_related("equipe"), many=True, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Ajouter une activité sur un lot",
        tags=["activités"],
        request=ActiviteCreationSerializer,
        description=(
            "Activité rattachée au lot de l'URL. Tout utilisateur connecté ayant accès "
            "au projet peut créer une activité. Libellé obligatoire ; quantité par défaut 1, "
            "unité U, dates et équipe facultatives. responsable_id désigne un utilisateur "
            "actif affecté au projet ; facultatif et nullable. "
            "Budget facultatif en centimes FCFA pour les statistiques pondérées. "
            "equipe_ids contient des UUID de collaborateurs du projet ; les équipes de "
            "chantier se rattachent ensuite via l'API d'affectations. Avancement automatique "
            "à 0 à la création, jusqu'à 100 selon les quantités réalisées."
            " Statut d'évolution facultatif : toute chaîne non vide envoyée par le frontend."
        ),
        examples=[
            OpenApiExample(
                "Activité minimale sans dates ni équipe",
                request_only=True,
                value={"libelle": "Terrassement des fondations"},
            ),
            OpenApiExample(
                "Nouvelle activité",
                request_only=True,
                value={
                    "libelle": "Carte_transport",
                    "statut": "À démarrer",
                    "motif": "En attente du matériel",
                    "quantite_prevue": "100.000",
                    "unite": "M2",
                    "date_debut_prevue": "2026-10-04",
                    "date_fin_prevue": "2026-10-11",
                    "responsable_id": None,
                    "equipe_ids": [],
                    "budget_initial_montant": 1000000,
                },
            ),
        ],
        responses={
            201: ActiviteSerializer,
            400: OpenApiResponse(description="Dates hors bornes du lot ou champs invalides."),
            **ERREURS_ACTIVITES,
        },
    )
    @transaction.atomic
    def post(self, request, lot_id):
        parent = get_object_or_404(Lot, pk=lot_id)
        self.check_object_permissions(request, parent)
        get_object_or_404(Projet.objects.select_for_update(), pk=parent.projet_id)
        lot = get_object_or_404(
            Lot.objects.select_related("projet")
            .filter(projet__supprime_le__isnull=True)
            .select_for_update(of=("self",)),
            pk=lot_id,
        )
        self.check_object_permissions(request, lot)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(lot.projet)
        if not lot.est_actif:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"lot": "Le lot est désactivé."})

        serializer = ActiviteCreationSerializer(
            data=request.data,
            context={"request": request, "lot": lot},
        )
        serializer.is_valid(raise_exception=True)
        activite = serializer.save()
        from apps.projets.services.sante_declencheur import declencher_recalcul_sante

        declencher_recalcul_sante(
            projet_id=lot.projet_id,
            declencheur_type="ACTIVITE_CREATION",
            declencheur_id=activite.id,
        )
        return Response(
            ActiviteSerializer(activite, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ActiviteDetailView(APIView):
    """Détail, modification partielle et suppression logique d'une activité."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("DELETE", "PUT", "PATCH"):
            return [
                IsAuthenticated(),
                GardePermissionProjet.pour("projets.ecrire")(),
            ]
        return [
            IsAuthenticated(),
            GardePermissionProjet.pour("projets.lire")(),
        ]

    def obtenir_activite(self, request, pk, verrou=False):
        queryset = Activite.objects.select_related("lot", "lot__projet").filter(
            lot__supprime_le__isnull=True,
            lot__projet__supprime_le__isnull=True,
        )
        activite = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(request, activite)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

            verifier_statut_projet_pour_ecriture(activite.lot.projet)
        if verrou:
            # Sérialise aussi les dépendances entre lots : projet, lot, activité.
            get_object_or_404(Projet.objects.select_for_update(), pk=activite.lot.projet_id)
            lot = get_object_or_404(Lot.objects.select_for_update(), pk=activite.lot_id)
            activite = get_object_or_404(queryset.select_for_update(of=("self",)), pk=pk)
            activite.lot = lot
        return activite

    @extend_schema(
        summary="Détail d'une activité",
        tags=["activités"],
        description=(
            "Accès au projet et permission de lecture du module Projets requis. "
            "Cette route permet de consulter (GET), modifier partiellement (PATCH) "
            "et supprimer logiquement (DELETE) une activité. Activation et "
            "désactivation via PATCH /api/v1/activites/{id}/activation/."
        ),
        responses={200: ActiviteSerializer, **ERREURS_ACTIVITES},
    )
    def get(self, request, pk):
        activite = self.obtenir_activite(request, pk)
        return Response(ActiviteSerializer(activite, context={"request": request}).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Supprimer logiquement une activité",
        tags=["activités"],
        description=(
            "Accès au projet et permission d'écriture du module Projets requis. "
            "Suppression logique : l'activité est conservée en base mais retirée "
            "des résultats courants. Retourne 204 sans corps de réponse. "
            "Cette opération est distincte d'une désactivation. Refus 400 si des "
            "activités non supprimées dépendent encore de cette activité."
        ),
        responses={204: OpenApiResponse(description="Activité supprimée."), **ERREURS_ACTIVITES},
    )
    @transaction.atomic
    def delete(self, request, pk):
        activite = self.obtenir_activite(request, pk, verrou=True)
        if activite.successeurs.exists():
            raise ValidationError(
                {"dependance": "Retirez les dépendances avant de supprimer cette activité."}
            )
        projet_id = activite.lot.projet_id if activite.lot else None
        activite.delete(utilisateur=request.user)
        if projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=projet_id,
                declencheur_type="ACTIVITE_SUPPRESSION",
                declencheur_id=activite.id,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Modifier une activité",
        tags=["activités"],
        description=(
            "Modification partielle ; permission d'écriture et accès au projet requis. "
            "Lot, réalisé, avancement et baseline immuables. Dates, équipe et "
            "dépendance validées sur l'état final. Dates prévisionnelles déjà "
            "renseignées : utilisez la reprogrammation avec motif et justification (RG-11)."
        ),
        request=ActiviteModificationSerializer,
        responses={200: ActiviteSerializer, **ERREURS_ACTIVITES},
        examples=[
            OpenApiExample("Renommer", value={"libelle": "Terrassement"}, request_only=True),
            OpenApiExample("Statut libre", value={"statut": "Terminé"}, request_only=True),
        ],
    )
    @transaction.atomic
    def patch(self, request, pk):
        activite = self.obtenir_activite(request, pk, verrou=True)
        serializer = ActiviteModificationSerializer(
            activite,
            data=request.data,
            partial=True,
            context={"request": request, "lot": activite.lot},
        )
        serializer.is_valid(raise_exception=True)
        activite_modifiee = serializer.save()
        if activite.lot and activite.lot.projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=activite.lot.projet_id,
                declencheur_type="ACTIVITE_MODIFICATION",
                declencheur_id=activite.id,
            )
        return Response(ActiviteSerializer(activite_modifiee, context={"request": request}).data)


class ActiviteActivationView(ActiviteDetailView):
    http_method_names = ["patch", "options"]

    @extend_schema(
        summary="Activer ou désactiver une activité",
        tags=["activités"],
        description=(
            "Permission d'écriture et accès au projet requis. Opération idempotente ; "
            "réactivation refusée si le lot est désactivé."
        ),
        request=ActivationSerializer,
        responses={200: ActiviteSerializer, **ERREURS_ACTIVITES},
        examples=[
            OpenApiExample("Désactiver", value={"est_actif": False}, request_only=True),
            OpenApiExample("Activer", value={"est_actif": True}, request_only=True),
        ],
    )
    @transaction.atomic
    def patch(self, request, pk):
        activite = self.obtenir_activite(request, pk, verrou=True)
        serializer = ActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        etat = serializer.validated_data["est_actif"]
        if etat and not activite.lot.est_actif:
            raise ValidationError({"lot": "Réactivez le lot avant l'activité."})
        activite.est_actif = etat
        activite.save(update_fields=["est_actif", "modifie_le"])
        if activite.lot and activite.lot.projet_id:
            from apps.projets.services.sante_declencheur import declencher_recalcul_sante

            declencher_recalcul_sante(
                projet_id=activite.lot.projet_id,
                declencheur_type="ACTIVITE_ACTIVATION",
                declencheur_id=activite.id,
            )
        return Response(ActiviteSerializer(activite, context={"request": request}).data)
