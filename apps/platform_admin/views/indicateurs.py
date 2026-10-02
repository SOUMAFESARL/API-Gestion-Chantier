"""Vues pour les indicateurs et tendances de la plateforme Super Admin."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.selectors.indicateurs import (
    obtenir_evolution_abonnements,
    obtenir_indicateurs_plateforme,
    obtenir_tendances_indicateurs,
)
from apps.platform_admin.serializers.indicateurs import (
    IndicateursPlateformeSerializer,
    PointEvolutionSerializer,
    TendanceIndicateurSerializer,
)

__all__ = [
    "EvolutionAbonnementsView",
    "IndicateursPlateformeView",
    "TendancesIndicateursView",
]


class IndicateursPlateformeView(APIView):
    """`GET /api/v1/indicateurs/` — Indicateurs consolidés de la plateforme (KPIs)."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = IndicateursPlateformeSerializer

    @extend_schema(
        tags=["admins-indicateurs"],
        summary="Indicateurs clés consolidés de la plateforme",
        description=(
            "Fournit les chiffres de pilotage globaux pour le tableau de bord de l'éditeur : "
            "nombre total d'entreprises clientes, actives, en période d'essai, impayées, "
            "ainsi que le Revenu Mensuel Récurrent (MRR) en centimes FCFA."
        ),
        responses={200: IndicateursPlateformeSerializer},
    )
    def get(self, request):
        donnees = obtenir_indicateurs_plateforme()
        serializer = self.serializer_class(donnees)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TendancesIndicateursView(APIView):
    """`GET /api/v1/indicateurs/tendances/` — Tendances historiques (sparklines) des indicateurs."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = TendanceIndicateurSerializer

    @extend_schema(
        tags=["admins-indicateurs"],
        summary="Tendances historiques et variations mensuelles",
        description=(
            "Renvoie pour chaque indicateur clé une série de 5 points chronologiques "
            "et la variation relative en % d'un mois sur l'autre pour alimenter les sparklines."
        ),
        responses={200: TendanceIndicateurSerializer(many=True)},
    )
    def get(self, request):
        donnees = obtenir_tendances_indicateurs()
        serializer = self.serializer_class(donnees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class EvolutionAbonnementsView(APIView):
    """`GET /api/v1/indicateurs/evolution/` — Série 90 jours des renouvellements d'abonnements."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = PointEvolutionSerializer

    @extend_schema(
        tags=["admins-indicateurs"],
        summary="Évolution des renouvellements d'abonnements sur 90 jours",
        description=(
            "Fournit jour par jour sur les 90 derniers jours le nombre d'abonnements renouvelés "
            "versus les abonnements non renouvelés pour alimenter le graphique d'activité du parc."
        ),
        responses={200: PointEvolutionSerializer(many=True)},
    )
    def get(self, request):
        donnees = obtenir_evolution_abonnements(nb_jours=90)
        serializer = self.serializer_class(donnees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
