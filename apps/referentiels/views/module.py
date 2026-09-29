"""Vue API pour la consultation du catalogue des modules souverains CCD Digital."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import MODULES_DETAILS, ModuleChoix, NiveauAcces
from apps.referentiels.serializers.module import ModuleItemSerializer

__all__ = ["ModuleListView"]


class ModuleListView(APIView):
    """`GET /api/v1/modules/` — Catalogue des 5 modules BTP souverains et de leurs droits."""

    permission_classes = [IsAuthenticated]
    serializer_class = ModuleItemSerializer

    @extend_schema(
        summary="Lister les modules BTP du socle",
        description=(
            "Renvoie la liste ordonnée des 5 modules souverains de CCD Digital avec leurs libellés officiels, "
            "descriptions métier, icônes recommandées et la liste complète des 4 niveaux d'accès RBAC supportés."
        ),
        responses={200: ModuleItemSerializer(many=True)},
    )
    def get(self, request):
        niveaux_supportes = [
            {
                "niveau": code,
                "code": NiveauAcces(code).name,
                "libelle": str(libelle),
            }
            for code, libelle in NiveauAcces.choices
        ]

        modules = []
        for code, libelle in ModuleChoix.choices:
            details = MODULES_DETAILS.get(code, {})
            modules.append(
                {
                    "code": code,
                    "libelle": str(libelle),
                    "description": details.get("description", ""),
                    "ordre": details.get("ordre", 99),
                    "icone": details.get("icone", "box"),
                    "niveaux_supportes": niveaux_supportes,
                }
            )

        modules.sort(key=lambda m: m["ordre"])
        serializer = ModuleItemSerializer(modules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
