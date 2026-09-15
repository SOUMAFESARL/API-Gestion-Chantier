"""Vue de signature d'un bon de paiement par le Directeur Général ou rôle autorisé."""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.core.enums import ActionAudit, RoleGlobal, StatutBonPaiement
from apps.finance.models import BonPaiement, SignatureBon
from apps.finance.serializers import (
    SignerBonPaiementRequestSerializer,
    SignerBonPaiementResponseSerializer,
)

__all__ = ["SignerBonPaiementView"]


class SignerBonPaiementView(APIView):
    """`POST /api/v1/finance/bons-paiement/<pk>/signer/`

    Permet au Directeur Général (ou Conducteur de Travaux / Directeur Financier)
    d'apposer sa signature électronique et de valider le bon de paiement.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SignerBonPaiementRequestSerializer

    @extend_schema(
        summary="Signer et valider un bon de paiement",
        description=(
            "Appose la signature électronique de l'utilisateur habilité (Directeur Général, "
            "Directeur Financier ou Conducteur de Travaux) et passe le bon de paiement à l'état SIGNE."
        ),
        request=SignerBonPaiementRequestSerializer,
        responses={
            200: SignerBonPaiementResponseSerializer,
            400: dict,
            403: dict,
            404: dict,
        },
    )
    def post(self, request, pk):
        bon = get_object_or_404(BonPaiement, pk=pk)

        # Contrôle du rôle : DG, CT ou DF
        role_utilisateur = getattr(request.user, "role_global", None)
        roles_autorises = [
            RoleGlobal.DIRECTEUR_GENERAL,
            RoleGlobal.ADMIN,
            RoleGlobal.CONDUCTEUR_TRAVAUX,
            RoleGlobal.DIRECTEUR_FINANCIER,
        ]

        if role_utilisateur not in roles_autorises:
            return Response(
                {
                    "code": "permission_refusee",
                    "message": "Seul le Directeur Général ou le Conducteur de Travaux est habilité à signer ce bon de paiement.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if bon.statut == StatutBonPaiement.SIGNE:
            return Response(
                {
                    "code": "deja_signe",
                    "message": "Ce bon de paiement est déjà signé.",
                    "id": str(bon.id),
                    "statut": bon.statut,
                },
                status=status.HTTP_200_OK,
            )

        commentaire = request.data.get("commentaire", "").strip()

        # Enregistrement de la signature
        SignatureBon.objects.create(
            bon_paiement=bon,
            signataire=request.user,
            niveau_requis=role_utilisateur or "DG",
            signe_le=timezone.now(),
            commentaire=commentaire,
        )

        statut_avant = bon.statut
        bon.statut = StatutBonPaiement.SIGNE
        bon.save(update_fields=["statut", "modifie_le"])

        # Journal d'audit conforme
        journaliser(
            action=ActionAudit.SIGNATURE,
            type_entite="BonPaiement",
            entite_id=bon.id,
            utilisateur_id=request.user.id,
            valeur_avant={"statut": statut_avant},
            valeur_apres={"statut": bon.statut, "signataire": str(request.user.id)},
            adresse_ip=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {
                "succes": True,
                "message": f"Bon de paiement {bon.numero} signé avec succès.",
                "id": str(bon.id),
                "numero": bon.numero,
                "statut": bon.statut,
                "signe_le": timezone.now().isoformat(),
            },
            status=status.HTTP_200_OK,
        )
