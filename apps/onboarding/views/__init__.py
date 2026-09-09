"""Les quatre endpoints de la configuration initiale — contrat T-024 §5.

**La ressource s'appelle `/configuration/`, pas `/wizard/`** — conventions A3 :
*« Langue des ressources : français sans accent. »* Et elle est **au
singulier** : c'est une ressource unique par schéma, pas une collection
(conventions §2.2, qui réserve le pluriel aux collections).

**Réservées à `AD`.** La configuration appartient à l'entreprise, et c'est
l'administrateur qui l'engage : un chef de projet qui appelle `valider` reçoit
un `403`, comme à l'écran, où la route ne lui est pas proposée.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import RoleGlobal
from apps.core.permissions import RoleRequis
from apps.onboarding.serializers import ProgressionSerializer
from apps.onboarding.services import lire_ou_creer, passer, terminer, valider

__all__ = [
    "ConfigurationView",
    "FranchirEtapeView",
    "PasserEtapeView",
    "RecapitulatifView",
    "TerminerView",
]

AdministrateurSeul = RoleRequis.pour(RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)

PARAMETRE_CODE = OpenApiParameter(
    name="code",
    location=OpenApiParameter.PATH,
    description="Code de l'étape : ENTREPRISE, PROJET ou EQUIPE. Jamais traduit.",
)


def _reponse(progression) -> Response:
    """Toute action renvoie la progression complète — §5.2.

    Un client qui reçoit `{"ok": true}` doit relire derrière : deux appels là
    où un suffit, et une fenêtre pendant laquelle son écran est en retard sur
    la base.
    """
    return Response(ProgressionSerializer(progression).data, status=status.HTTP_200_OK)


class ConfigurationView(APIView):
    """`GET /api/v1/configuration/` — où en est la configuration.

    **La ressource est créée à la première lecture** si elle n'existe pas.
    L'effet de bord n'est pas observable du client, qui reçoit dans les deux
    cas une progression à 0 % : il n'a donc pas à connaître l'ordre entre sa
    première lecture et sa première écriture.
    """

    permission_classes = [AdministrateurSeul]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lire la progression de configuration",
        responses={200: ProgressionSerializer},
    )
    def get(self, request):
        return _reponse(lire_ou_creer())


class FranchirEtapeView(APIView):
    """`POST /api/v1/configuration/etapes/{code}/valider/`.

    **N'écrit aucune donnée métier** (R-98). L'entreprise, le projet et les
    invitations ont déjà été créés par leurs propres endpoints ; celui-ci
    enregistre le franchissement, rien d'autre.
    """

    permission_classes = [AdministrateurSeul]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Valider une étape",
        parameters=[PARAMETRE_CODE],
        request=None,
        responses={200: ProgressionSerializer},
    )
    def post(self, request, code: str):
        return _reponse(
            valider(
                code=code,
                utilisateur=request.user,
                adresse_ip=request.META.get("REMOTE_ADDR"),
            )
        )


class PasserEtapeView(APIView):
    """`POST /api/v1/configuration/etapes/{code}/passer/`.

    Identique à `valider`, `mode = PASSEE`. **Refusé sur `ENTREPRISE` et
    `PROJET`** : un espace sans entreprise renseignée ni projet n'a rien à
    montrer — `422 etape_non_facultative`.
    """

    permission_classes = [AdministrateurSeul]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Passer une étape facultative",
        parameters=[PARAMETRE_CODE],
        request=None,
        responses={200: ProgressionSerializer},
    )
    def post(self, request, code: str):
        return _reponse(
            passer(
                code=code,
                utilisateur=request.user,
                adresse_ip=request.META.get("REMOTE_ADDR"),
            )
        )


class TerminerView(APIView):
    """`POST /api/v1/configuration/terminer/` — *Accéder au tableau de bord*.

    **Il ne fait rien de plus que constater** : le franchissement de la
    dernière étape a déjà basculé le statut. Il existe pour le seul cas où
    l'utilisateur a fermé l'onglet avant l'écran de confirmation — l'appel
    répond alors `200` sans rien changer.
    """

    permission_classes = [AdministrateurSeul]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Terminer la configuration",
        request=None,
        responses={200: ProgressionSerializer},
    )
    def post(self, request):
        return _reponse(
            terminer(
                utilisateur=request.user,
                adresse_ip=request.META.get("REMOTE_ADDR"),
            )
        )


class RecapitulatifView(APIView):
    """`GET /api/v1/configuration/recapitulatif/` — Récapitulatif pour l'écran de confirmation."""

    permission_classes = [AdministrateurSeul]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lire le récapitulatif de la configuration",
        responses={200: None},
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        entreprise_data = None
        if tenant and tenant.schema_name != "public":
            from apps.tenants.serializers import EntrepriseSerializer

            entreprise_data = EntrepriseSerializer(tenant).data

        from apps.projets.models import Projet
        from apps.projets.serializers import ProjetSerializer

        projet = Projet.objects.all().order_by("-cree_le").first()
        projet_data = ProjetSerializer(projet).data if projet else None

        from apps.accounts.models import Invitation

        invitations_count = Invitation.objects.count()

        return Response(
            {
                "entreprise": entreprise_data,
                "projet": projet_data,
                "reference": projet.reference if projet else None,
                "invitations": invitations_count,
            },
            status=status.HTTP_200_OK,
        )
