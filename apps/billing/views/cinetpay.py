"""Vues API pour l'intégration de paiement CinetPay et catalogue des forfaits BTP."""

import logging

from django.db import connection
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Abonnement, PaiementAbonnement, Plan
from apps.billing.serializers import (
    AnnulerPaiementRequestSerializer,
    AnnulerPaiementResponseSerializer,
    InitierPaiementRequestSerializer,
    InitierPaiementResponseSerializer,
    PlanCatalogueSerializer,
    StatutPaiementResponseSerializer,
)
from apps.billing.services.cinetpay import CinetPayClient
from apps.billing.services.paiement import PaiementAbonnementService, PaiementEnCoursError

logger = logging.getLogger(__name__)

__all__ = [
    "AnnulerPaiementView",
    "CinetPayWebhookView",
    "InitierPaiementView",
    "PlansCatalogueView",
    "StatutPaiementView",
]


class PlansCatalogueView(APIView):
    """`GET /api/v1/billing/plans/` — Liste des forfaits BTP proposés."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Catalogue des forfaits BTP",
        responses={200: PlanCatalogueSerializer(many=True)},
    )
    def get(self, request):
        with schema_context(get_public_schema_name()):
            plans = Plan.objects.filter(est_actif=True).order_by("prix_mensuel_montant")
            serializer = PlanCatalogueSerializer(plans, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)


class InitierPaiementView(APIView):
    """`POST /api/v1/billing/cinetpay/initier/` — Démarre une session de paiement CinetPay."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Initier un paiement d'abonnement CinetPay",
        request=InitierPaiementRequestSerializer,
        responses={200: InitierPaiementResponseSerializer},
    )
    def post(self, request):
        serializer = InitierPaiementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_code = serializer.validated_data["plan_code"]
        cycle = serializer.validated_data["cycle"]
        return_url = serializer.validated_data.get("return_url")

        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            # Fallback vers l'entreprise de l'utilisateur si disponible
            tenant = getattr(request.user, "entreprise", None)

        if tenant is None:
            return Response(
                {"detail": "Aucune entreprise active identifiée pour cette requête."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with schema_context(get_public_schema_name()):
            plan = Plan.objects.filter(code=plan_code).first()
            if not plan:
                return Response(
                    {"detail": f"Forfait « {plan_code} » introuvable."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            try:
                resultat = PaiementAbonnementService.initier_paiement(
                    entreprise=tenant,
                    plan=plan,
                    cycle=cycle,
                    user_email=request.user.email,
                    user_name=f"{request.user.prenom} {request.user.nom}".strip(),
                    return_url=return_url,
                )
            except PaiementEnCoursError as e:
                logger.warning(
                    f"Tentative de réinitiation alors qu'un paiement est en cours : {e}"
                )
                return Response(
                    {
                        "detail": str(e),
                        "code": "PAIEMENT_EN_COURS",
                        "transaction_en_cours": e.transaction_en_cours,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'initiation du paiement CinetPay : {e}")
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        resp_serializer = InitierPaiementResponseSerializer(resultat)
        return Response(resp_serializer.data, status=status.HTTP_200_OK)


class AnnulerPaiementView(APIView):
    """`POST /api/v1/billing/cinetpay/annuler/` — Abandon explicite d'une tentative en cours (Option A2)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Annuler explicitement une session de paiement CinetPay en cours",
        request=AnnulerPaiementRequestSerializer,
        responses={
            200: AnnulerPaiementResponseSerializer,
            400: dict,
            404: dict,
        },
    )
    def post(self, request):
        serializer = AnnulerPaiementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transaction_id = serializer.validated_data["transaction_id"]
        motif = serializer.validated_data.get("motif", "Annulation demandée par l'utilisateur")

        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            tenant = getattr(request.user, "entreprise", None)

        if tenant is None:
            return Response(
                {"detail": "Aucune entreprise active identifiée pour cette requête."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with schema_context(get_public_schema_name()):
            try:
                resultat = PaiementAbonnementService.annuler_paiement_en_cours(
                    entreprise=tenant,
                    transaction_id=transaction_id,
                    motif=motif,
                )
            except ValueError as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'annulation du paiement {transaction_id} : {e}")
                return Response(
                    {"detail": f"Erreur lors de l'annulation : {e}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        resp_serializer = AnnulerPaiementResponseSerializer(resultat)
        return Response(resp_serializer.data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class CinetPayWebhookView(APIView):
    """`POST /api/v1/billing/cinetpay/webhook/`

    Réception sécurisée et idempotente des notifications CinetPay (IPN).
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Webhook IPN CinetPay (notification de paiement)",
        responses={200: dict},
    )
    def post(self, request):
        # 1. Vérification de l'authenticité de la notification via X-Token (HMAC SHA-256)
        client = CinetPayClient()
        x_token = request.headers.get("x-token") or request.META.get("HTTP_X_TOKEN")

        if not client.verifier_signature(request.body, x_token):
            logger.warning("Notification CinetPay rejetée : signature HMAC (X-Token) invalide.")
            return Response(
                {"status": "REJECTED", "message": "Signature de notification invalide."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # CinetPay peut poster en application/x-www-form-urlencoded ou application/json
        payload = request.data or {}

        # 2. Récupération de l'identifiant de transaction (selon conventions CinetPay)
        transaction_id = (
            payload.get("cpm_trans_id")
            or payload.get("transaction_id")
            or payload.get("cpm_custom")
            or request.GET.get("transaction_id")
        )

        if not transaction_id:
            logger.warning(f"Webhook CinetPay reçu sans identifiant de transaction : {payload}")
            return Response(
                {"status": "IGNORED", "message": "Identifiant de transaction manquant."},
                status=status.HTTP_200_OK,
            )

        logger.info(f"Notification IPN CinetPay reçue pour transaction : {transaction_id}")

        resultat = PaiementAbonnementService.traiter_notification_webhook(
            transaction_id=str(transaction_id),
            donnees_webhook=payload,
        )

        # Si le site_id était invalide, renvoyer 400
        if resultat.get("statut") == "SITE_INVALIDE":
            return Response(resultat, status=status.HTTP_400_BAD_REQUEST)

        # CinetPay exige impérativement un HTTP 200 pour considérer la notification reçue
        return Response(resultat, status=status.HTTP_200_OK)


class StatutPaiementView(APIView):
    """`GET /api/v1/billing/cinetpay/statut/<transaction_id>/`

    Consultation de l'état d'un paiement pour le retour frontend.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Consulter le statut d'un paiement CinetPay",
        responses={200: StatutPaiementResponseSerializer},
    )
    def get(self, request, transaction_id: str):
        with schema_context(get_public_schema_name()):
            paiement = (
                PaiementAbonnement.objects.filter(reference_transaction=transaction_id)
                .select_related("facture__abonnement__plan", "facture__entreprise")
                .first()
            )

            if not paiement:
                paiement = (
                    PaiementAbonnement.objects.filter(reference_commande=transaction_id)
                    .select_related("facture__abonnement__plan", "facture__entreprise")
                    .first()
                )

            if not paiement:
                return Response(
                    {"detail": f"Transaction « {transaction_id} » introuvable."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Si le statut est encore INITIE ou EN_ATTENTE_OPERATEUR, tenter une vérification instantanée auprès de CinetPay
            # afin d'offrir une réactivité immédiate à l'utilisateur qui vient d'être redirigé
            if paiement.statut in [
                PaiementAbonnement.Statut.INITIE,
                PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR,
            ]:
                PaiementAbonnementService.traiter_notification_webhook(transaction_id)
                paiement.refresh_from_db()

            abonnement = paiement.facture.abonnement
            est_actif = (
                abonnement.statut == Abonnement.Statut.ACTIF
                and paiement.statut == PaiementAbonnement.Statut.CONFIRME
            )

            data = {
                "transaction_id": transaction_id,
                "statut": paiement.statut,
                "statut_affichage": paiement.get_statut_display(),
                "mode_paiement": paiement.get_mode_display(),
                "moyen_paiement": paiement.get_mode_display(),
                "montant_fcfa": paiement.montant_fcfa,
                "numero_facture": paiement.facture.numero,
                "reference_facture": paiement.facture.numero,
                "paye_le": paiement.paye_le,
                "abonnement_actif": est_actif,
                "est_valide": est_actif,
                "date_fin": abonnement.date_fin if est_actif else None,
                "abonnement_expire_le": (
                    abonnement.date_fin.isoformat() if est_actif and abonnement.date_fin else None
                ),
                "entreprise": paiement.facture.entreprise.raison_sociale,
                "plan": abonnement.plan.libelle,
            }

            serializer = StatutPaiementResponseSerializer(data)
            return Response(serializer.data, status=status.HTTP_200_OK)
