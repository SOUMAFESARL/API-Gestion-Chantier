"""Vue des données du planning (Gantt) d'un projet (SFD F3 §5.2, §5.3, §13).

Le planning suit l'arbre : chaque case porte ses propres dates (baseline si complète, sinon
prévues), son physique et son temporel, et ses enfants. Le périmètre de lecture s'applique comme
pour l'arbre : sans `projets.voir_tout`, on voit ses branches et le chemin qui y mène.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.selectors.arbre_api import COMPLET, visibilite
from apps.projets.services.indicateurs_temporels import calendrier_pour_elements
from apps.projets.services.sante_calculs import calculer_arbre, calculer_temporels_arbre

__all__ = ["ProjetCourbeView", "ProjetPlanningView"]


class PlanningCaseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    libelle = serializers.CharField()
    numero = serializers.CharField(allow_null=True)
    niveau = serializers.CharField(allow_null=True)
    debut = serializers.DateField(allow_null=True)
    fin = serializers.DateField(allow_null=True)
    avancement = serializers.FloatField(allow_null=True)
    avancement_temporel = serializers.FloatField(allow_null=True)
    delta_retard = serializers.FloatField(allow_null=True)
    statut = serializers.CharField()
    acces = serializers.CharField()
    enfants = serializers.ListField(child=serializers.DictField())


class PlanningSerializer(serializers.Serializer):
    aujourdhui = serializers.DateField()
    cases = PlanningCaseSerializer(many=True)


def _dates_contractuelles(element) -> tuple[str | None, str | None]:
    """Baseline si la paire est complète, sinon dates prévues (ISO ou None)."""
    if element.date_debut_baseline and element.date_fin_baseline:
        debut, fin = element.date_debut_baseline, element.date_fin_baseline
    else:
        debut, fin = element.date_debut_prevue, element.date_fin_prevue
    return (
        debut.isoformat() if debut else None,
        fin.isoformat() if fin else None,
    )


def _arrondi(valeur) -> float | None:
    return None if valeur is None else round(float(valeur), 1)


class ProjetPlanningView(APIView):
    """`GET /api/v1/projets/{id}/planning/` — payload minimal pour le Gantt mobile."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Données du planning (Gantt) d'un projet",
        tags=["projets"],
        description=(
            "Payload minimal pour la 3G : les cases actives de l'arbre, imbriquées, dates "
            "contractuelles (baseline si complète, sinon prévues) au format ISO, pourcentages "
            "arrondis à 1 décimale. Le périmètre de lecture s'applique."
        ),
        responses={
            200: PlanningSerializer,
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)

        arbre = charger_arbre(projet, actifs_seulement=True)
        acces = visibilite(arbre, request.user, request)
        aujourdhui = timezone.localdate()
        calendrier = calendrier_pour_elements([projet, *arbre.elements], aujourdhui)
        resultats = calculer_arbre(arbre)
        temporels = calculer_temporels_arbre(arbre, resultats, aujourdhui, calendrier)
        numeros = arbre.numerotation()

        def case(element):
            debut, fin = _dates_contractuelles(element)
            resultat = resultats.get(element.pk)
            physique = resultat.physique if resultat else None
            temporel = temporels.get(element.pk)
            complet = acces[element.pk] == COMPLET
            niveau = arbre.niveau(element)
            return {
                "id": element.pk,
                "libelle": element.libelle,
                "numero": numeros.get(element.pk),
                "niveau": niveau.libelle if niveau else None,
                "debut": debut if complet else None,
                "fin": fin if complet else None,
                "avancement": _arrondi(physique) if complet else None,
                "avancement_temporel": _arrondi(temporel) if complet else None,
                "delta_retard": (
                    _arrondi(temporel - physique)
                    if complet and temporel is not None and physique is not None
                    else None
                ),
                "statut": element.statut,
                "acces": acces[element.pk],
                "enfants": [case(e) for e in arbre.enfants_actifs(element) if e.pk in acces],
            }

        donnees = {
            "aujourdhui": aujourdhui.isoformat(),
            "cases": [case(e) for e in arbre.racines() if e.pk in acces],
        }
        return Response(PlanningSerializer(donnees).data, status=status.HTTP_200_OK)


class ProjetCourbeView(APIView):
    """`GET /api/v1/projets/{id}/courbe/?element=<id>` — la courbe en S (30/10/2026).

    Le prévu (dates et montants), le réel (relevés de nuit et valeur du jour) et la fin estimée
    au rythme des 4 dernières semaines, affichée seulement. Sans `element` : le projet entier.
    """

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        summary="Courbe en S d'un projet ou d'une case",
        tags=["projets"],
        parameters=[OpenApiParameter("element", str, description="Une case ; vide : le projet.")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, pk):
        from apps.projets.models import Element
        from apps.projets.services.courbe import courbe

        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        element = None
        if request.query_params.get("element"):
            element = get_object_or_404(Element, pk=request.query_params["element"], projet=projet)
            acces = visibilite(charger_arbre(projet), request.user, request)
            if acces.get(element.pk) != COMPLET:
                raise PermissionDenied("Cette case est en dehors de votre périmètre.")
        return Response(courbe(projet, element))
