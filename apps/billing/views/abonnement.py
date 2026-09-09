"""Vue pour la consultation de l'abonnement et de l'essai gratuit — T-025 §8."""

from datetime import timedelta

from django.db import connection
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import JOURS_ESSAI, Abonnement, Plan
from apps.billing.serializers import AbonnementSerializer

__all__ = ["AbonnementView"]


class AbonnementView(APIView):
    """`GET /api/v1/abonnement/` — Consultation du statut d'abonnement / essai."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Consulter l'abonnement ou l'essai gratuit de l'entreprise",
        responses={200: AbonnementSerializer},
    )
    def get(self, request):
        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            return Response(
                {"detail": "Aucun tenant actif."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with schema_context(get_public_schema_name()):
            abonnement = Abonnement.objects.filter(entreprise=tenant).select_related("plan").first()

            # Auto-provisionnement de l'essai si manquant (ex: compte créé avant la migration)
            if abonnement is None:
                plan_pro = Plan.objects.filter(code=Plan.Code.PRO).first()
                if not plan_pro:
                    plan_pro = Plan.objects.create(
                        code=Plan.Code.PRO,
                        libelle="Pro",
                        limite_projets=20,
                        limite_utilisateurs=10,
                        limite_stockage_mo=5000,
                        acces_ia=True,
                        est_actif=True,
                    )
                aujourdhui = timezone.localdate()
                abonnement = Abonnement.objects.create(
                    entreprise=tenant,
                    plan=plan_pro,
                    date_debut=aujourdhui,
                    date_fin=aujourdhui + timedelta(days=JOURS_ESSAI),
                    fin_essai=aujourdhui + timedelta(days=JOURS_ESSAI),
                    statut=Abonnement.Statut.ESSAI,
                )

            serializer = AbonnementSerializer(abonnement)
            return Response(serializer.data, status=status.HTTP_200_OK)
