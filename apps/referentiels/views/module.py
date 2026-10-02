"""Vue API pour la consultation du catalogue des modules souverains CCD Digital."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models import CatalogueModule, EntrepriseModule
from apps.accounts.models import Module
from apps.accounts.services.roles import (
    initialiser_modules_par_defaut,
    initialiser_permissions_par_defaut,
)
from apps.core.enums import NiveauAcces
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
            "descriptions métier, icônes recommandées, autorisations granulaires dynamiques et niveaux RBAC."
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

        tenant = getattr(request, "tenant", None)
        if tenant and getattr(tenant, "schema_name", "public") != "public":
            modules_souscrits = EntrepriseModule.objects.filter(
                entreprise=tenant,
                est_actif=True,
                supprime_le__isnull=True,
            ).values_list("module_id", flat=True)

            modules_qs = (
                CatalogueModule.objects.filter(
                    id__in=modules_souscrits,
                    est_actif=True,
                    supprime_le__isnull=True,
                )
                .prefetch_related("permissions")
                .order_by("ordre", "code")
            )
            if not modules_qs.exists():
                modules_qs = (
                    CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
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
                initialiser_permissions_par_defaut()
                modules_qs = (
                    CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
                    .prefetch_related("permissions")
                    .order_by("ordre", "code")
                )

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
            ]

            # Accès par défaut normalisés pour le frontend Next.js
            perms_codes_set = {p["code"] for p in perms_data}
            acces_defaut = []
            if "LECTURE" in perms_codes_set:
                acces_defaut.append("lecture")
            if "ECRITURE" in perms_codes_set:
                acces_defaut.append("saisie")
            if "VALIDATION" in perms_codes_set:
                acces_defaut.append("validation")

            modules.append(
                {
                    "id": str(m.id),
                    "code": m.code,
                    "libelle": m.libelle,
                    "description": m.description,
                    "ordre": m.ordre,
                    "icone": m.icone,
                    "statut": "ACTIF" if m.est_actif else "INACTIF",
                    "acces_par_defaut": acces_defaut,
                    "permissions": perms_data,
                    "permissions_codes": [p["code"] for p in perms_data],
                    "niveaux_supportes": niveaux_supportes,
                }
            )

        serializer = ModuleItemSerializer(modules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
