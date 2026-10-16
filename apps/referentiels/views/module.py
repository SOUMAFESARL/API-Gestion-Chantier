"""Vue API pour la consultation du catalogue des modules souverains CCD Digital."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models import CatalogueModule
from apps.accounts.models import Module
from apps.accounts.services.roles import (
    initialiser_modules_par_defaut,
)
from apps.referentiels.serializers.module import ModuleItemSerializer

__all__ = ["ModuleListView"]


class ModuleListView(APIView):
    """`GET /api/v1/modules/` — Catalogue des modules BTP souverains et de leurs droits dynamiques."""

    permission_classes = [IsAuthenticated]
    serializer_class = ModuleItemSerializer

    @extend_schema(
        summary="Lister les modules BTP du socle",
        description=(
            "Renvoie la liste ordonnée des modules souverains de CCD Digital avec leurs libellés officiels, "
            "descriptions métier, icônes recommandées et autorisations granulaires dynamiques."
        ),
        responses={200: ModuleItemSerializer(many=True)},
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant and getattr(tenant, "schema_name", "public") != "public":
            # Même règle que les droits réels : tout module actif du catalogue, sauf ceux que le
            # super admin a désactivés pour cette entreprise. « Administration » n'est pas un
            # module qu'on souscrit : il reste hors de cette liste.
            from apps.core.droits import MODULES_SYSTEME, _obtenir_modules_actifs

            codes_actifs = _obtenir_modules_actifs(tenant) - MODULES_SYSTEME
            ids_actifs = [
                m.id
                for m in CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
                if m.code.lower() in codes_actifs
            ]
            modules_qs = (
                CatalogueModule.objects.filter(id__in=ids_actifs)
                .prefetch_related("permissions")
                .order_by("ordre", "code")
            )
        else:
            modules_qs = (
                CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
                .prefetch_related("permissions")
                .order_by("ordre", "code")
            )

        if not modules_qs.exists():
            modules_qs = (
                Module.objects.filter(est_actif=True, supprime_le__isnull=True)
                .prefetch_related("permissions")
                .order_by("ordre", "code")
            )
            if not modules_qs.exists():
                initialiser_modules_par_defaut()
                modules_qs = (
                    CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
                    .prefetch_related("permissions")
                    .order_by("ordre", "code")
                )

        from apps.core.droits import permissions_effectives

        perms_utilisateur = permissions_effectives(request.user, request=request)

        modules = []
        for m in modules_qs:
            perms_qs = m.permissions.filter(est_actif=True, supprime_le__isnull=True).order_by("ordre", "code")

            perms_data = [
                {
                    "id": p.id,
                    "code": p.code,
                    "libelle": p.libelle,
                    "description": p.description,
                    "ordre": p.ordre,
                }
                for p in perms_qs
                if p.code in perms_utilisateur
            ]

            if not perms_data:
                continue

            modules.append(
                {
                    "id": str(m.id),
                    "code": m.code,
                    "libelle": m.libelle,
                    "description": m.description,
                    "ordre": m.ordre,
                    "icone": m.icone,
                    "statut": "ACTIF" if m.est_actif else "INACTIF",
                    "permissions": perms_data,
                    "permissions_codes": [p["code"] for p in perms_data],
                }
            )

        serializer = ModuleItemSerializer(modules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
