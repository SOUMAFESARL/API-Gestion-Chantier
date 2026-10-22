"""Vue des données du planning (Gantt) d'un projet (SFD F3 §5.2, §5.3, §13)."""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Activite, Lot, Projet
from apps.projets.services.indicateurs_temporels import (
    calendrier_pour_lots,
    indicateurs_temporels_lot,
)
from apps.projets.services.sante_calculs import (
    calculer_avancement_physique_activite,
    calculer_avancement_physique_lot,
)

__all__ = ["ProjetPlanningView"]


class PlanningActiviteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    libelle = serializers.CharField()
    debut = serializers.DateField(allow_null=True)
    fin = serializers.DateField(allow_null=True)
    avancement = serializers.FloatField()
    statut = serializers.CharField()


class PlanningLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    libelle = serializers.CharField()
    debut = serializers.DateField(allow_null=True)
    fin = serializers.DateField(allow_null=True)
    avancement = serializers.FloatField()
    avancement_temporel = serializers.FloatField(allow_null=True)
    delta_retard = serializers.FloatField(allow_null=True)
    activites = PlanningActiviteSerializer(many=True)


class PlanningSerializer(serializers.Serializer):
    aujourdhui = serializers.DateField()
    lots = PlanningLotSerializer(many=True)


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
            "Payload minimal pour la 3G : lots et activités actifs triés par ordre, "
            "dates contractuelles (baseline si complète, sinon prévues) au format ISO, "
            "pourcentages arrondis à 1 décimale. Mêmes droits que le détail du projet."
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

        lots = list(
            Lot.objects.filter(projet=projet, est_actif=True)
            .order_by("ordre", "code")
            .prefetch_related(
                Prefetch(
                    "activites",
                    queryset=Activite.objects.filter(est_actif=True).order_by("ordre", "cree_le"),
                )
            )
        )

        aujourdhui = timezone.localdate()
        calendrier = calendrier_pour_lots(lots, aujourdhui)

        donnees_lots = []
        for lot in lots:
            indicateurs = indicateurs_temporels_lot(lot, aujourdhui, calendrier)
            debut, fin = _dates_contractuelles(lot)
            activites = []
            for activite in lot.activites.all():
                a_debut, a_fin = _dates_contractuelles(activite)
                activites.append(
                    {
                        "id": activite.id,
                        "libelle": activite.libelle,
                        "debut": a_debut,
                        "fin": a_fin,
                        "avancement": _arrondi(calculer_avancement_physique_activite(activite)),
                        "statut": activite.statut,
                    }
                )
            donnees_lots.append(
                {
                    "id": lot.id,
                    "code": lot.code,
                    "libelle": lot.libelle,
                    "debut": debut,
                    "fin": fin,
                    "avancement": _arrondi(calculer_avancement_physique_lot(lot)),
                    "avancement_temporel": _arrondi(indicateurs["avancement_temporel"]),
                    "delta_retard": _arrondi(indicateurs["delta_retard"]),
                    "activites": activites,
                }
            )

        donnees = {"aujourdhui": aujourdhui.isoformat(), "lots": donnees_lots}
        return Response(PlanningSerializer(donnees).data, status=status.HTTP_200_OK)
