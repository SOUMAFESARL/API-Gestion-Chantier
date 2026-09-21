"""Vues de l'inscription — contrat T-021.

**Les cinq endpoints vivent sur le domaine de la plateforme**, schéma `public`,
et jamais sur un sous-domaine client : au moment de l'inscription, le client n'a
pas encore de sous-domaine.

Les vues ne décident de rien : elles valident la forme, appellent le service, et
répondent. Les issues d'échec remontent en exceptions, mises en forme par le
gestionnaire d'erreurs commun.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ValidationDjango
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.tenants.models import DUREE_LIEN_ACTIVATION, DemandeInscription
from apps.tenants.serializers import (
    AccuseActivationSerializer,
    AccuseInscriptionSerializer,
    ActivationSerializer,
    ContenuJetonInscriptionSerializer,
    DepotInscriptionSerializer,
    EntrepriseSerializer,
    EtatProvisionnementResponseSerializer,
    RenvoiActivationResponseSerializer,
    RenvoiSerializer,
    VerificationJetonInscriptionSerializer,
)
from apps.tenants.services.inscription import activer, deposer, renvoyer, verifier

__all__ = [
    "ActivationView",
    "DepotInscriptionView",
    "EntrepriseView",
    "EtatProvisionnementView",
    "RenvoiActivationView",
    "VerificationJetonInscriptionView",
]


def _reste(demande: DemandeInscription) -> int:
    return max(0, int((demande.expire_le - timezone.now()).total_seconds()))


class DepotInscriptionView(APIView):
    """`POST /api/v1/inscription/` — déposer une demande.

    **`202`, toujours.** `201 Created` signifierait « la ressource existe, la
    voici » ; or rien n'a été créé du point de vue du client — ni entreprise,
    ni schéma, ni compte, seulement une demande qui expirera en 48 h si
    personne ne lit l'email. C'est aussi la seule réponse qui reste vraie dans
    les cinq branches du §2.4, et donc la seule qui n'énumère pas.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription"
    serializer_class = DepotInscriptionSerializer

    @extend_schema(
        summary="Déposer une demande d'inscription",
        description="Enregistre la demande d'inscription d'une nouvelle entreprise et déclenche l'envoi d'un email contenant le lien d'activation.",
        request=DepotInscriptionSerializer,
        responses={202: AccuseInscriptionSerializer, 400: dict},
    )
    def post(self, request):
        serializer = DepotInscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        demande = deposer(
            identifiant=donnees.get("id"),
            raison_sociale=donnees["raison_sociale"],
            pays=donnees["pays"],
            email=donnees["email"],
            ip=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {
                "id": str(demande.pk),
                "statut": DemandeInscription.Statut.EN_ATTENTE,
                "email": demande.email,
                "expire_dans": int(DUREE_LIEN_ACTIVATION.total_seconds()),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RenvoiActivationView(APIView):
    """`POST /api/v1/inscription/renvoyer/` — nouveau jeton, ancien invalidé.

    Un identifiant inconnu reçoit **le même `202`**, sans email.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_renvoi"
    serializer_class = RenvoiSerializer

    @extend_schema(
        summary="Renvoyer l'email d'activation",
        description="Génère un nouveau jeton d'activation et réexpédie l'email tout en invalidant le précédent.",
        request=RenvoiSerializer,
        responses={202: RenvoiActivationResponseSerializer, 400: dict},
    )
    def post(self, request):
        serializer = RenvoiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        renvoyer(serializer.validated_data["id"])
        return Response({"statut": "EN_ATTENTE"}, status=status.HTTP_202_ACCEPTED)


class VerificationJetonInscriptionView(APIView):
    """`POST /api/v1/inscription/verifier/` — **sans consommer** le jeton (R-83)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_verifier"
    serializer_class = VerificationJetonInscriptionSerializer

    @extend_schema(
        summary="Lire le contenu d'un jeton d'activation",
        description="Vérifie la validité d'un jeton reçu par email et renvoie les informations pré-remplies sans le consommer.",
        request=VerificationJetonInscriptionSerializer,
        responses={200: ContenuJetonInscriptionSerializer, 400: dict, 410: dict},
    )
    def post(self, request):
        serializer = VerificationJetonInscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        demande = verifier(serializer.validated_data["jeton"])
        return Response(
            {
                "raison_sociale": demande.raison_sociale,
                "email": demande.email,
                "pays": demande.pays,
                "expire_dans": _reste(demande),
            }
        )


class ActivationView(APIView):
    """`POST /api/v1/inscription/activer/` — consomme le jeton, lance le provisioning."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_activer"
    serializer_class = ActivationSerializer

    @extend_schema(
        summary="Activer un espace",
        description="Valide le mot de passe de l'administrateur, consomme définitivement le jeton d'activation et enclenche la création asynchrone du schéma tenant et du compte.",
        request=ActivationSerializer,
        responses={202: AccuseActivationSerializer, 400: dict},
    )
    def post(self, request):
        serializer = ActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        # La complexité est jugée **avant** de consommer le jeton : un mot de
        # passe refusé ne doit pas coûter le lien à celui qui le corrige.
        try:
            validate_password(donnees["mot_de_passe"])
        except ValidationDjango as erreur:
            raise erreur

        demande = activer(
            donnees["jeton"],
            nom=donnees["nom"],
            prenom=donnees.get("prenom", ""),
            mot_de_passe=donnees["mot_de_passe"],
        )

        return Response(
            {"suivi": str(demande.pk), "statut": DemandeInscription.Statut.PROVISIONNEMENT},
            status=status.HTTP_202_ACCEPTED,
        )


class EtatProvisionnementView(APIView):
    """`GET /api/v1/inscription/etat/{suivi}/` — la sonde de l'écran d'attente.

    **`ECHEC` répond `200`, et ce n'est pas une négligence.** La requête a
    réussi : elle demandait un état, elle l'a obtenu. Un `500` dirait que la
    *sonde* est en panne, et le client réessaierait indéfiniment un endpoint
    qu'il croit cassé. Le statut HTTP décrit le sort de la requête ; le champ
    `statut` décrit le sort du provisionnement — les confondre rend les deux
    illisibles.

    **`url_connexion` est le seul endroit où le slug apparaît**, et seulement
    après consommation du jeton : pour quelqu'un qui a prouvé qu'il lit la
    boîte mail.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_etat"
    serializer_class = EtatProvisionnementResponseSerializer

    @extend_schema(
        summary="Suivre le provisionnement",
        description="Sonde de vérification de l'état d'avancement du déploiement du schéma tenant de l'entreprise.",
        responses={200: EtatProvisionnementResponseSerializer, 404: dict},
    )
    def get(self, request, suivi):
        demande = DemandeInscription.objects.filter(pk=suivi).first()
        if demande is None:
            return Response(
                {"erreur": {"code": "introuvable", "message": _("Suivi inconnu."), "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if demande.statut == DemandeInscription.Statut.ACTIVEE and demande.entreprise_id:
            base_url = "http://localhost:3000"
            url_connexion = f"{base_url}/connexion"

            return Response(
                {"statut": "PRET", "url_connexion": url_connexion}
            )

        if demande.statut == DemandeInscription.Statut.ECHEC:
            return Response({"statut": "ECHEC"})

        return Response({"statut": "PROVISIONNEMENT"})


class EntrepriseView(APIView):
    """`GET` et `PATCH /api/v1/entreprise/` — Étape 1 du Wizard & Paramètres."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        summary="Lire les informations de l'entreprise cliente",
        responses={200: EntrepriseSerializer},
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None or tenant.schema_name == "public":
            return Response(
                {"detail": _("Aucun tenant résolu.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = EntrepriseSerializer(tenant, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier les informations de l'entreprise cliente",
        request=EntrepriseSerializer,
        responses={200: EntrepriseSerializer},
    )
    def patch(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None or tenant.schema_name == "public":
            return Response(
                {"detail": _("Aucun tenant résolu.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = EntrepriseSerializer(
            instance=tenant,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        donnees = dict(serializer.validated_data)
        fichier_logo = donnees.pop("fichier_logo", None)
        retirer_logo = donnees.pop("retirer_logo", False)
        fond_retire = None

        if fichier_logo:
            from apps.tenants.services.images import traiter_logo_entreprise

            resultat_logo = traiter_logo_entreprise(
                fichier_ou_flux=fichier_logo,
                tenant_schema=tenant.schema_name,
                nom_origine=fichier_logo.name,
            )
            # Les trois variantes sont conservées. Le 24 px et le 48 px sont
            # taillés pour les deux densités d'écran de la barre ; l'original
            # recadré sert aux documents. Le service les produisait déjà tous
            # les trois — seul le 48 était retenu.
            tenant.logo = resultat_logo["cle_2x"]
            tenant.logo_1x = resultat_logo["cle_1x"]
            tenant.logo_original = resultat_logo["cle_original"]
            fond_retire = resultat_logo["fond_retire"]
            if not donnees.get("couleur_primaire"):
                tenant.couleur_primaire = resultat_logo["dominant_color"]

        elif retirer_logo:
            tenant.logo = ""
            tenant.logo_1x = ""
            tenant.logo_original = ""

        for champ, valeur in donnees.items():
            setattr(tenant, champ, valeur)

        tenant.save()

        retour = EntrepriseSerializer(tenant, context={"request": request})
        corps = dict(retour.data)
        if fond_retire is not None:
            # Transitoire, jamais stocké : l'information n'a de sens qu'au
            # retour de l'envoi. Elle permet à l'écran de dire « le fond de
            # votre logo n'a pas pu être détouré » au lieu de laisser
            # découvrir un rectangle blanc dans la barre, trois écrans plus loin.
            corps["fond_retire"] = fond_retire
        return Response(corps, status=status.HTTP_200_OK)
