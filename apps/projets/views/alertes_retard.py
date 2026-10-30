"""Vues API pour les alertes de retard (SFD F3 §5.4, §10 et Erratum E-3)."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.core.droits import est_dg
from apps.core.enums import ActionAudit, RoleProjet
from apps.core.exceptions import ErreurMetier
from apps.core.ip_restriction import extraire_ip_client
from apps.core.pagination import PaginationStandard
from apps.projets.models import AffectationProjet, AlerteRetard, StatutAlerteRetard
from apps.projets.serializers.alertes_retard import (
    AlerteRetardResolutionSerializer,
    AlerteRetardSerializer,
)

__all__ = [
    "AlerteRetardListView",
    "AlerteRetardResoudreView",
    "est_cp_du_projet",
    "est_do",
]


def est_do(utilisateur) -> bool:
    """Détermine si l'utilisateur a le rôle de Directeur des Opérations (DO)."""
    if not utilisateur or not getattr(utilisateur, "is_authenticated", False):
        return False
    if getattr(utilisateur, "role_global", None) in ("DO", "DIRECTEUR_OPERATIONS"):
        return True
    role = getattr(utilisateur, "role", None)
    if role and getattr(role, "code", "") == "DO":
        return True
    role_p = getattr(utilisateur, "role_personnalise", None)
    return bool(role_p and getattr(role_p, "code", "") == "DO")


def est_cp_du_projet(utilisateur, projet) -> bool:
    """Détermine si l'utilisateur est le Chef de Projet assigné au projet."""
    if not utilisateur or not getattr(utilisateur, "is_authenticated", False) or not projet:
        return False
    if getattr(projet, "chef_projet_id", None) == utilisateur.pk:
        return True
    return AffectationProjet.objects.filter(
        projet=projet,
        utilisateur=utilisateur,
        est_actif=True,
        supprime_le__isnull=True,
        role_projet__in=[RoleProjet.CHEF_PROJET, "CP", "CHEF_PROJET"],
    ).exists()


class AlerteRetardListView(APIView):
    """`GET /api/v1/alertes-retard/` — Liste paginée des alertes de retard."""

    pagination_class = PaginationStandard
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Lister les alertes de retard",
        tags=["alertes-retard"],
        description=(
            "Liste paginée des alertes de retard. "
            "Périmètre : le DG et le DO voient toutes les alertes de l'entreprise ; "
            "les autres collaborateurs ne voient que les alertes dont ils sont destinataires. "
            "Filtres disponibles : niveau, projet (id), statut."
        ),
        parameters=[
            OpenApiParameter(
                name="niveau",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filtrer par niveau de criticité (MODERE, ELEVE, CRITIQUE).",
            ),
            OpenApiParameter(
                name="projet",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filtrer par identifiant UUID du projet.",
            ),
            OpenApiParameter(
                name="statut",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filtrer par statut (OUVERTE, EN_COURS, RESOLUE, IGNOREE).",
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Numéro de page.",
            ),
            OpenApiParameter(
                name="taille_page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Nombre d'éléments par page (défaut 20, max 100).",
            ),
        ],
        responses={
            200: AlerteRetardSerializer(many=True),
            401: OpenApiResponse(description="Non authentifié."),
        },
    )
    def get(self, request):
        user = request.user

        # Périmètre : DG et DO voient tout, les autres uniquement leurs alertes destinataires
        if est_dg(user) or est_do(user) or user.is_superuser:
            qs = AlerteRetard.objects.filter(
                supprime_le__isnull=True,
                projet__supprime_le__isnull=True,
            )
        else:
            qs = AlerteRetard.objects.filter(
                supprime_le__isnull=True,
                projet__supprime_le__isnull=True,
                destinataires=user,
            ).distinct()

        # Filtres
        niveau = request.query_params.get("niveau")
        if niveau:
            niveaux = [n.strip().upper() for n in niveau.split(",") if n.strip()]
            if len(niveaux) == 1:
                qs = qs.filter(niveau=niveaux[0])
            elif len(niveaux) > 1:
                qs = qs.filter(niveau__in=niveaux)

        projet_param = (
            request.query_params.get("projet") or request.query_params.get("projet_id")
        )
        if projet_param:
            qs = qs.filter(projet_id=projet_param.strip())

        statut_param = request.query_params.get("statut")
        if statut_param:
            statuts = [s.strip().upper() for s in statut_param.split(",") if s.strip()]
            if len(statuts) == 1:
                qs = qs.filter(statut=statuts[0])
            elif len(statuts) > 1:
                qs = qs.filter(statut__in=statuts)

        qs = qs.select_related("projet", "element", "element__niveau", "resolue_par").order_by(
            "-date_detection", "-cree_le"
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = AlerteRetardSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = AlerteRetardSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AlerteRetardResoudreView(APIView):
    """`PATCH /api/v1/alertes-retard/{id}/resoudre/` — Résoudre une alerte de retard."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Résoudre une alerte de retard",
        tags=["alertes-retard"],
        description=(
            "Résout une alerte de retard avec un commentaire justificatif "
            "(au moins 10 caractères). "
            "Seuls le Chef de Projet (CP) du projet concerné et le "
            "Directeur des Opérations (DO) peuvent résoudre l'alerte. "
            "Le Directeur Général (DG) n'est pas habilité à résoudre. "
            "L'action renseigne statut=RESOLUE, resolue_par, resolue_le "
            "et est journalisée dans l'audit log."
        ),
        request=AlerteRetardResolutionSerializer,
        responses={
            200: AlerteRetardSerializer,
            400: OpenApiResponse(description="Commentaire manquant ou inférieur à 10 caractères."),
            401: OpenApiResponse(description="Non authentifié."),
            403: OpenApiResponse(
                description="Non autorisé (le DG ou tout rôle autre que CP/DO du projet)."
            ),
            404: OpenApiResponse(description="Alerte introuvable."),
            422: OpenApiResponse(description="Alerte déjà résolue ou ignorée."),
        },
    )
    def patch(self, request, pk):
        alerte = get_object_or_404(
            AlerteRetard.objects.select_related("projet", "element", "element__niveau", "resolue_par"),
            pk=pk,
            supprime_le__isnull=True,
            projet__supprime_le__isnull=True,
        )

        user = request.user

        # 1. Le DG ne peut PAS résoudre (SFD §3 : le DG NON)
        if est_dg(user):
            raise PermissionDenied(
                "Le Directeur Général n'est pas autorisé à résoudre une alerte de retard."
            )

        # 2. Seuls le CP du projet et le DO peuvent résoudre
        if not (est_do(user) or est_cp_du_projet(user, alerte.projet)):
            raise PermissionDenied(
                "Seuls le Chef de Projet du projet concerné et un "
                "Directeur des Opérations (DO) peuvent résoudre cette alerte."
            )

        # 3. Validation du corps de requête (commentaire obligatoire >= 10 caractères)
        serializer = AlerteRetardResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        commentaire = serializer.validated_data["commentaire_resolution"]

        # 4. Règle métier : une alerte déjà RESOLUE ou IGNOREE renvoie ErreurMetier (422)
        if alerte.statut in (StatutAlerteRetard.RESOLUE, StatutAlerteRetard.IGNOREE):
            raise ErreurMetier("Cette alerte de retard est déjà résolue ou ignorée.")

        # 5. Enregistrement de la résolution
        moment = timezone.now()
        statut_avant = alerte.statut

        with transaction.atomic():
            alerte.statut = StatutAlerteRetard.RESOLUE
            alerte.commentaire_resolution = commentaire
            alerte.resolue_par = user
            alerte.resolue_le = moment
            alerte.save(
                update_fields=[
                    "statut",
                    "commentaire_resolution",
                    "resolue_par",
                    "resolue_le",
                    "modifie_le",
                ]
            )

            # 6. Trace d'audit
            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="AlerteRetard",
                entite_id=alerte.id,
                utilisateur_id=user.id,
                valeur_avant={"statut": statut_avant},
                valeur_apres={
                    "statut": StatutAlerteRetard.RESOLUE,
                    "commentaire_resolution": commentaire,
                    "resolue_par_id": str(user.id),
                    "resolue_le": moment.isoformat(),
                },
                adresse_ip=extraire_ip_client(request),
                appareil=request.headers.get("User-Agent", "")[:255],
            )

        return Response(AlerteRetardSerializer(alerte).data, status=status.HTTP_200_OK)
