"""Paramètres de la plateforme : tarifs des forfaits et identité (nom, logo)."""

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Plan
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.models.identite import IdentitePlateforme
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.serializers.parametres import (
    CODES_FORFAITS,
    OCTETS_LOGO_MAX,
    TYPES_LOGO,
    EcritureTarifsSerializer,
    tarif_public,
)


def _exiger_superviseur(request) -> None:
    """Seul un superviseur règle la plateforme ; un agent SUPPORT la consulte."""
    if not getattr(request.user, "is_superuser", False):
        raise PermissionDenied(_("Seul un superviseur de la plateforme peut modifier ce réglage."))


def _journaliser(request, action: str, detail: dict) -> None:
    with schema_context(get_public_schema_name()):
        JournalPlateforme.objects.create(
            utilisateur_id=request.user.id,
            action=action,
            detail=detail,
            adresse_ip=request.META.get("REMOTE_ADDR"),
            appareil=request.headers.get("User-Agent", "")[:255],
        )


def _identite_publique(request) -> dict:
    identite = IdentitePlateforme.obtenir()
    logo = request.build_absolute_uri(identite.logo.url) if identite.logo else None
    return {"nom": identite.nom, "logo_url": logo}


class TarifsPublicsView(APIView):
    """`GET /api/v1/plateforme/tarifs/` — les forfaits proposés, sans connexion."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    @extend_schema(summary="Tarifs publics des forfaits", responses={200: dict})
    def get(self, request):
        with schema_context(get_public_schema_name()):
            plans = Plan.objects.filter(
                est_actif=True,
                code__in=[c.value for c in CODES_FORFAITS],
                prix_mensuel_montant__isnull=False,
            ).order_by("prix_mensuel_montant")
            return Response([tarif_public(p) for p in plans], status=status.HTTP_200_OK)


class IdentitePublicView(APIView):
    """`GET /api/v1/plateforme/identite/` — nom et logo de la plateforme, sans connexion."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []

    @extend_schema(summary="Identité publique de la plateforme", responses={200: dict})
    def get(self, request):
        with schema_context(get_public_schema_name()):
            return Response(_identite_publique(request), status=status.HTTP_200_OK)


class AdminTarifsView(APIView):
    """`PUT /api/v1/admins/parametres/tarifs/` — enregistre les forfaits d'un coup."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(summary="Enregistrer les tarifs des forfaits", request=EcritureTarifsSerializer)
    def put(self, request):
        _exiger_superviseur(request)
        serializer = EcritureTarifsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        demandes = serializer.validated_data["tarifs"]

        with schema_context(get_public_schema_name()), transaction.atomic():
            plans = {p.code: p for p in Plan.objects.select_for_update().filter(
                code__in=[d["plan_code"] for d in demandes]
            )}
            for demande in demandes:
                plan = plans.get(demande["plan_code"])
                if plan is None:
                    raise ValidationError({"tarifs": [_("Le forfait %(code)s n'existe pas.") % {"code": demande["plan_code"]}]})
                plan.libelle = demande["libelle"]
                plan.prix_mensuel_montant = demande["prix_mensuel_centimes"]
                plan.prix_annuel_montant = demande["prix_annuel_centimes"]
                plan.limite_projets = demande["limite_chantiers"]
                plan.limite_utilisateurs = demande["limite_utilisateurs"]
                plan.limite_stockage_mo = demande["limite_stockage_go"] * 1024
                plan.limites_avancees = {
                    **(plan.limites_avancees or {}),
                    "remise_annuelle_pourcent": demande["remise_annuelle_pourcent"],
                    "avantages": [dict(a) for a in demande["avantages"]],
                }
                plan.save()

        _journaliser(request, "MODIFICATION_TARIFS", {"forfaits": sorted(plans)})
        with schema_context(get_public_schema_name()):
            lus = Plan.objects.filter(code__in=list(plans)).order_by("prix_mensuel_montant")
            return Response([tarif_public(p) for p in lus], status=status.HTTP_200_OK)

    def patch(self, request):
        """Alias de `PUT` : le client HTTP du frontend n'expose que PATCH pour les écritures."""
        return self.put(request)


class AdminIdentiteView(APIView):
    """`PATCH /api/v1/admins/parametres/identite/` — nom et logo (multipart) de la plateforme."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(summary="Modifier l'identité de la plateforme")
    def patch(self, request):
        _exiger_superviseur(request)
        nom = request.data.get("nom")
        fichier = request.FILES.get("logo")
        retirer = str(request.data.get("retirer_logo", "")).lower() in ("true", "1")

        if nom is not None and not str(nom).strip():
            raise ValidationError({"nom": [_("Le nom de la plateforme est requis.")]})
        if nom is not None and len(str(nom).strip()) > 120:
            raise ValidationError({"nom": [_("Le nom ne peut pas dépasser 120 caractères.")]})
        if fichier is not None:
            if fichier.content_type not in TYPES_LOGO:
                raise ValidationError({"logo": [_("Le logo doit être une image PNG, JPEG, WebP ou SVG.")]})
            if fichier.size > OCTETS_LOGO_MAX:
                raise ValidationError({"logo": [_("Le logo ne peut pas dépasser 2 Mo.")]})

        with schema_context(get_public_schema_name()):
            identite = IdentitePlateforme.obtenir()
            if nom is not None:
                identite.nom = str(nom).strip()
            if fichier is not None:
                identite.logo = fichier
            elif retirer:
                identite.logo = None
            identite.save()
            reponse = _identite_publique(request)

        _journaliser(request, "MODIFICATION_IDENTITE_PLATEFORME", {"nom": reponse["nom"], "logo": bool(reponse["logo_url"])})
        return Response(reponse, status=status.HTTP_200_OK)
