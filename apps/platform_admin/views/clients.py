"""Vues pour la gestion des entreprises clientes de la plateforme par le Super Admin."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.ip_restriction import extraire_ip_client
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.selectors.clients import (
    lister_clients_plateforme,
    obtenir_fiche_client,
)
from apps.platform_admin.serializers.clients import (
    ChangerPlanClientRequestSerializer,
    ClientPlateformeSerializer,
    SuspendreClientRequestSerializer,
)
from apps.platform_admin.serializers.impersonation import (
    ErreurPlateformeResponseSerializer,
)
from apps.platform_admin.services.clients import (
    changer_plan_client_plateforme,
    reactiver_client_plateforme,
    suspendre_client_plateforme,
)

__all__ = [
    "ChangerPlanClientPlateformeView",
    "ClientsPlateformeListView",
    "FicheClientPlateformeView",
    "ReactiverClientPlateformeView",
    "SuspendreClientPlateformeView",
]

PARAM_CLIENT_ID = OpenApiParameter(
    name="client_id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    description="Identifiant UUID unique de l'entreprise cliente.",
)

EXEMPLE_CLIENT_ACTIF = {
    "id": "233683d2-e56d-446e-ac60-3f457490745f",
    "raison_sociale": "Nouvelle Entreprise BTP SARL",
    "nom_commercial": "Nouvelle Entreprise BTP",
    "slug": "nouvelle_entreprise_btp",
    "pays": "CI",
    "ville": "Abidjan",
    "email_contact": "dg@nouvelle-entreprise.ci",
    "telephone_contact": "+2250102030405",
    "statut": "ACTIF",
    "cree_le": "2026-09-16T11:22:55.502784Z",
    "active_le": "2026-09-16T11:22:54.828813Z",
    "nb_utilisateurs": 4,
    "nb_projets": 2,
    "abonnement": {
        "statut": "ACTIF",
        "plan_code": "BATISSEUR",
        "reference_transaction": "TXN-52D334BE",
        "montant_mensuel_centimes": 1900000,
        "date_debut": "2026-09-01",
        "date_fin": "2027-08-31",
        "fin_essai": None,
        "renouvellement_auto": True,
    },
}

EXEMPLE_CLIENT_SUSPENDU = {
    **EXEMPLE_CLIENT_ACTIF,
    "statut": "SUSPENDU",
    "abonnement": {
        **EXEMPLE_CLIENT_ACTIF["abonnement"],
        "statut": "SUSPENDU",
        "renouvellement_auto": False,
    },
}


class ClientsPlateformeListView(APIView):
    """`GET /api/v1/clients/` — Liste complète des entreprises clientes de la plateforme."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = ClientPlateformeSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Liste des entreprises clientes de la plateforme",
        description=(
            "Renvoie la liste consolidée de toutes les entreprises clientes inscrites sur la "
            "plateforme, avec leur statut, leur forfait BTP en cours, leur date de création et "
            "leurs compteurs d'usage réels (nombre d'utilisateurs et nombre de chantiers actifs).\n\n"
            "Prend en charge le filtrage par recherche plein texte via `?recherche=` ou `?q=`."
        ),
        parameters=[
            OpenApiParameter(
                name="recherche",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtrer par raison sociale, nom commercial, slug, email ou ville.",
            ),
            OpenApiParameter(
                name="q",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Alias court de 'recherche'.",
            ),
        ],
        responses={
            200: ClientPlateformeSerializer(many=True),
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Liste des clients avec abonnements et métriques",
                value=[EXEMPLE_CLIENT_ACTIF],
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request):
        terme = (
            request.query_params.get("recherche")
            or request.query_params.get("q")
            or request.query_params.get("search")
        )
        donnees = lister_clients_plateforme(terme_recherche=terme)
        serializer = self.serializer_class(donnees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FicheClientPlateformeView(APIView):
    """`GET /api/v1/clients/{client_id}/` — Consultation détaillée de la fiche client."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = ClientPlateformeSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Détail complet d'une entreprise cliente (Fiche Client)",
        description=(
            "Renvoie les informations complètes d'une entreprise cliente : identité juridique, "
            "coordonnées, état et historique de son abonnement, ainsi que ses compteurs d'usage "
            "réels (utilisateurs et chantiers du schéma tenant)."
        ),
        parameters=[PARAM_CLIENT_ID],
        responses={
            200: ClientPlateformeSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Fiche client détaillée complète",
                value=EXEMPLE_CLIENT_ACTIF,
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Client introuvable",
                value={
                    "detail": "Entreprise cliente introuvable."
                },
                response_only=True,
                status_codes=["404"],
            ),
        ],
    )
    def get(self, request, client_id):
        donnees = obtenir_fiche_client(client_id)
        serializer = self.serializer_class(donnees)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SuspendreClientPlateformeView(APIView):
    """`POST /api/v1/clients/{client_id}/suspendre/` — Suspension d'un client par le Super Admin."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = SuspendreClientRequestSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Suspendre une entreprise cliente",
        description=(
            "Suspend l'accès d'une entreprise cliente et de son abonnement en cours. "
            "Exige la transmission d'un motif obligatoire.\n\n"
            "L'opération est tracée de façon immuable dans le `JournalPlateforme` "
            "avec l'identifiant du Super Admin, l'adresse IP et le motif fourni."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=SuspendreClientRequestSerializer,
        responses={
            200: ClientPlateformeSerializer,
            400: ErreurPlateformeResponseSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
            409: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Corps de requête pour suspension",
                value={"motif": "Non-paiement après mise en demeure et relances multiples."},
                request_only=True,
            ),
            OpenApiExample(
                "Réponse après suspension réussie",
                value=EXEMPLE_CLIENT_SUSPENDU,
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Erreur de conflit si déjà suspendue",
                value={
                    "erreur": {
                        "code": "conflit",
                        "message": "Cette entreprise cliente est déjà suspendue.",
                        "details": {},
                    }
                },
                response_only=True,
                status_codes=["409"],
            ),
        ],
    )
    def post(self, request, client_id):
        serializer = SuspendreClientRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        motif = serializer.validated_data["motif"]
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        client_actualise = suspendre_client_plateforme(
            entreprise_id=client_id,
            motif=motif,
            admin_user=request.user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse_serializer = ClientPlateformeSerializer(client_actualise)
        return Response(reponse_serializer.data, status=status.HTTP_200_OK)


class ReactiverClientPlateformeView(APIView):
    """`POST /api/v1/clients/{client_id}/reactiver/` — Réactivation d'une entreprise cliente."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = ClientPlateformeSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Réactiver une entreprise cliente suspendue",
        description=(
            "Rétablit l'accès et l'abonnement d'une entreprise précédemment suspendue.\n\n"
            "Si la période d'essai est toujours valide, l'abonnement repasse à `ESSAI`, "
            "sinon il est rétabli à `ACTIF` avec renouvellement automatique activé.\n\n"
            "Ne nécessite aucun corps de requête.\n\n"
            "L'opération est tracée de façon immuable dans le `JournalPlateforme`."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=None,
        responses={
            200: ClientPlateformeSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
            409: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Réponse après réactivation réussie",
                value=EXEMPLE_CLIENT_ACTIF,
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Erreur si l'entreprise n'est pas suspendue",
                value={
                    "erreur": {
                        "code": "conflit",
                        "message": "Seule une entreprise suspendue peut être réactivée.",
                        "details": {},
                    }
                },
                response_only=True,
                status_codes=["409"],
            ),
        ],
    )
    def post(self, request, client_id):
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        client_actualise = reactiver_client_plateforme(
            entreprise_id=client_id,
            admin_user=request.user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse_serializer = ClientPlateformeSerializer(client_actualise)
        return Response(reponse_serializer.data, status=status.HTTP_200_OK)


class ChangerPlanClientPlateformeView(APIView):
    """`PATCH / POST /api/v1/clients/{client_id}/abonnement/` — Modification du forfait du client."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]
    serializer_class = ChangerPlanClientRequestSerializer

    @extend_schema(
        tags=["admins-clients"],
        summary="Modifier le forfait d'une entreprise cliente",
        description=(
            "Met à jour le plan d'abonnement d'une entreprise cliente ainsi que son tarif mensuel.\n\n"
            "Accepte indifféremment :\n"
            "- Les codes canoniques : `DEMARRAGE`, `BATISSEUR`, `MAITRE_OEUVRE`\n"
            "- Les alias d'interface : `starter`, `pro`, `enterprise`\n\n"
            "Accessible via `PATCH` (recommandé REST) ou `POST` (alias pratique pour frontend).\n\n"
            "L'opération est tracée de façon immuable dans le `JournalPlateforme`."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=ChangerPlanClientRequestSerializer,
        responses={
            200: ClientPlateformeSerializer,
            400: ErreurPlateformeResponseSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Corps de requête pour changement de forfait",
                value={"plan_code": "BATISSEUR"},
                request_only=True,
            ),
            OpenApiExample(
                "Corps avec alias frontend supporté",
                value={"plan_code": "pro"},
                request_only=True,
            ),
            OpenApiExample(
                "Réponse après mise à jour du forfait",
                value=EXEMPLE_CLIENT_ACTIF,
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Plan invalide ou inconnu",
                value={
                    "plan_code": [
                        "Plan inconnu : INVALIDE. Choix possibles : DEMARRAGE, BATISSEUR, MAITRE_OEUVRE."
                    ]
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def patch(self, request, client_id):
        serializer = ChangerPlanClientRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_code = serializer.validated_data["plan_code"]
        adresse_ip = extraire_ip_client(request)
        appareil = request.headers.get("User-Agent", "")[:255]

        client_actualise = changer_plan_client_plateforme(
            entreprise_id=client_id,
            code_plan=plan_code,
            admin_user=request.user,
            adresse_ip=adresse_ip,
            appareil=appareil,
        )

        reponse_serializer = ClientPlateformeSerializer(client_actualise)
        return Response(reponse_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["admins-clients"],
        summary="Modifier le forfait d'une entreprise cliente (alias POST)",
        description=(
            "Alias de l'endpoint PATCH pour les clients frontend préférant les requêtes POST. "
            "Met à jour le plan d'abonnement d'une entreprise cliente ainsi que son tarif mensuel."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=ChangerPlanClientRequestSerializer,
        responses={
            200: ClientPlateformeSerializer,
            400: ErreurPlateformeResponseSerializer,
            401: ErreurPlateformeResponseSerializer,
            403: ErreurPlateformeResponseSerializer,
            404: ErreurPlateformeResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Corps de requête pour changement de forfait",
                value={"plan_code": "BATISSEUR"},
                request_only=True,
            ),
        ],
    )
    def post(self, request, client_id):
        """Permet l'appel en POST ou PATCH indifféremment."""
        return self.patch(request, client_id)
