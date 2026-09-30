"""Vue API pour la consultation du catalogue des modules souverains CCD Digital."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Module
from apps.accounts.services.roles import initialiser_modules_par_defaut
from apps.core.enums import NiveauAcces
from apps.referentiels.serializers.module import ModuleItemSerializer

__all__ = ["ModuleListView"]


class ModuleListView(APIView):
    """`GET /api/v1/modules/` — Catalogue des modules BTP souverains et de leurs droits."""

    permission_classes = [IsAuthenticated]
    serializer_class = ModuleItemSerializer

    @extend_schema(
        summary="Lister les modules BTP du socle",
        description=(
            "Renvoie la liste ordonnée des modules souverains de CCD Digital avec leurs libellés officiels, "
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

        modules_qs = Module.objects.filter(
            est_actif=True, supprime_le__isnull=True
        ).order_by("ordre", "code")

        if not modules_qs.exists():
            initialiser_modules_par_defaut()
            modules_qs = Module.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).order_by("ordre", "code")

        modules = [
            {
                "code": m.code,
                "libelle": m.libelle,
                "description": m.description,
                "ordre": m.ordre,
                "icone": m.icone,
                "niveaux_supportes": niveaux_supportes,
            }
            for m in modules_qs
        ]

        serializer = ModuleItemSerializer(modules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
